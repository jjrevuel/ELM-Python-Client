##
## © Copyright 2021- IBM Inc. All rights reserved
# SPDX-License-Identifier: MIT
##


# RQM OSLC API https://jazz.net/wiki/bin/view/Main/RqmOslcQmV2Api

import logging
import re

import anytree
import lxml.etree as ET
import requests
import tqdm

from . import _app
from . import _project
from . import _typesystem
from . import oslcqueryapi
from . import rdfxml
from . import server
from . import utils

#################################################################################################

logger = logging.getLogger(__name__)

#################################################################################################


class _QMProject(_project._Project):
    # A QM project
    def __init__(self, name, project_uri, app, is_optin=False, singlemode=False,defaultinit=True):
        super().__init__(name, project_uri, app, is_optin,singlemode,defaultinit=defaultinit)
        self._components = None  # keyed on component uri
        self._configurations = None # keyed on the config name
        self._folders = None
        self._foldersnotyetloaded = None
        self.is_singlemode = False # this is only true if config enabled is true and single mode is true
        self.gcconfiguri = None
        self.default_query_resource = "oslc_qm:TestCaseQuery"

    def load_components_and_configurations(self,force=False):
        if self._components is not None and self._configurations is not None and not force:
            return
        self._components = {}
        self._configurations = {}
        ncomps = 0
        nconfs = 0
        # retrieve components and configurations for this project
        if not self.is_optin:
            logger.debug( f"{self.is_optin=}" )
            # get the default configuration
            projx = self.execute_get_xml(self.reluri('rm-projects/' + self.iid))
            compsu = rdfxml.xmlrdf_get_resource_text( projx, './/jp06:components' )
            compsx = self.execute_get_xml(compsu)
            defaultcompu = rdfxml.xmlrdf_get_resource_uri( compsx, './/oslc_config:component' )

            # register the only component
            ncomps += 1
            self._components[defaultcompu] = {'name': self.name, 'configurations': {}}
            thisconfu = defaultcompu+"/configurations"
            configs = self.execute_get_json(thisconfu)
            configdetails = configs[defaultcompu+"/configurations"]
            if type(configs[thisconfu]["http://www.w3.org/2000/01/rdf-schema#member"])==dict:
                confs = [configs[thisconfu]["http://www.w3.org/2000/01/rdf-schema#member"]]
            else:
                confs = configs[thisconfu]["http://www.w3.org/2000/01/rdf-schema#member"]
            for aconf in confs:
                confu = aconf['value']
                confx = self.execute_get_xml(confu)
                conftitle = rdfxml.xmlrdf_get_resource_text(confx,'.//dcterms:title')
                conftype = 'Stream' if 'stream' in confu else 'Baseline'
                self._components[defaultcompu]['configurations'][confu] = {'name': conftitle, 'conftype': conftype, 'confXml': confx}
                self._configurations[defaultcompu] = self._components[defaultcompu]['configurations'][confu]
                nconfs += 1
        elif self.singlemode:
            logger.debug( f"{self.singlemode=}" )
            #get the single component from a QueryCapability
            # <oslc:QueryCapability>
            #    <oslc_config:component rdf:resource="https://mb02-calm.rtp.raleigh.ibm.com:9443/rm/cm/component/_ln_roBIOEeumc4tx0skHCA"/>
            #    <oslc:resourceType rdf:resource="http://jazz.net/ns/rm/dng/view#View"/>
            #    <oslc:queryBase rdf:resource="https://mb02-calm.rtp.raleigh.ibm.com:9443/rm/views_oslc/query?componentURI=https%3A%2F%2Fmb02-calm.rtp.raleigh.ibm.com%3A9443%2Frm%2Fcm%2Fcomponent%2F_ln_roBIOEeumc4tx0skHCA"/>
            #    <dcterms:title rdf:datatype="http://www.w3.org/2001/XMLSchema#string">View Definition Query Capability</dcterms:title>
            # </oslc:QueryCapability>

            px = self.execute_get_xml(self.project_uri)

            sx = self.get_services_xml()
            assert sx is not None, "sx is None"
            compuri = rdfxml.xmlrdf_get_resource_uri(sx, ".//oslc:QueryCapability/oslc_config:component")
            assert compuri is not None, "compuri is None"

            ncomps += 1
            self._components[compuri] = {'name': self.name, 'configurations': {}}
            configs = self.execute_get_xml(compuri+"/configurations")
            for conf in rdfxml.xml_find_elements(configs,'.//rdfs:member'):
                confu = rdfxml.xmlrdf_get_resource_uri(conf)
                thisconfx = self.execute_get_xml(confu)
                conftitle= rdfxml.xmlrdf_get_resource_text(thisconfx,'.//dcterms:title')
                # e.g. http://open-services.net/ns/config#Stream
                isstr = rdfxml.xml_find_element( thisconfx,'.//oslc_config:Stream' )
                if isstr is None:
                    conftype = "Baseline"
                else:
                    conftype = "Stream"
                self._components[compuri]['configurations'][confu] = {'name': conftitle, 'conftype': conftype, 'confXml': thisconfx}
                self._configurations[confu] = self._components[compuri]['configurations'][confu]
                nconfs += 1
            self._configurations = self._components[compuri]['configurations']
        else: # full optin
            logger.debug( f"full optin" )
            cmsp_xml = self.app.retrieve_cm_service_provider_xml()
            logger.info( f"cmsp=",ET.tostring(cmsp_xml) )
#  <rdf:Description rdf:nodeID="A4">
#    <oslc:resourceType rdf:resource="http://open-services.net/ns/config#Component"/>
#    <oslc:queryBase rdf:resource="https://jazz.ibm.com:9443/qm/oslc_config/resources/com.ibm.team.vvc.Component"/>
#    <oslc:resourceShape rdf:resource="https://jazz.ibm.com:9443/qm/oslc_config/resourceShapes/com.ibm.team.vvc.Component"/>
#    <dcterms:title rdf:parseType="Literal">Default query capability for Component</dcterms:title>
#    <rdf:type rdf:resource="http://open-services.net/ns/core#QueryCapability"/>
#  </rdf:Description>

            components_uri = rdfxml.xmlrdf_get_resource_uri(cmsp_xml, './/rdf:Description/rdf:type[@rdf:resource="http://open-services.net/ns/core#QueryCapability"]/../oslc:resourceType[@rdf:resource="http://open-services.net/ns/config#Component"]/../oslc:queryBase')
            logger.info( f"{components_uri=}" )
            # get all components
            crx = self.execute_get_xml(components_uri)

#      <oslc_config:Component rdf:about="https://jazz.ibm.com:9443/qm/oslc_config/resources/com.ibm.team.vvc.Component/_iw4s4EB3Eeus6Zk4qsm_Cw">
#        <dcterms:title rdf:parseType="Literal">SGC Agile</dcterms:title>
#        <oslc:instanceShape rdf:resource="https://jazz.ibm.com:9443/qm/oslc_config/resourceShapes/com.ibm.team.vvc.Component"/>
#        <dcterms:identifier>_iw4s4EB3Eeus6Zk4qsm_Cw</dcterms:identifier>
#        <dcterms:modified rdf:datatype="http://www.w3.org/2001/XMLSchema#dateTime">2020-12-17T14:52:54.318Z</dcterms:modified>
#        <oslc_config:configurations rdf:resource="https://jazz.ibm.com:9443/qm/oslc_config/resources/com.ibm.team.vvc.Component/_iw4s4EB3Eeus6Zk4qsm_Cw/configurations"/>
#        <acc:accessContext rdf:resource="https://jazz.ibm.com:9443/qm/acclist#_rikP0EB1Eeus6Zk4qsm_Cw"/>
#        <process:projectArea rdf:resource="https://jazz.ibm.com:9443/qm/process/project-areas/_rikP0EB1Eeus6Zk4qsm_Cw"/>
#        <oslc:serviceProvider rdf:resource="https://jazz.ibm.com:9443/qm/oslc_config/serviceProviders/configuration"/>
#        <dcterms:relation rdf:resource="https://jazz.ibm.com:9443/qm/service/com.ibm.rqm.integration.service.IIntegrationService/resources/_rikP0EB1Eeus6Zk4qsm_Cw/component/_iw4s4EB3Eeus6Zk4qsm_Cw"/>
#      </oslc_config:Component>

            for component_el in rdfxml.xml_find_elements(crx, f'.//oslc_config:Component/process:projectArea[@rdf:resource="{self.project_uri}"]/..'):
                logger.info( f"{component_el=}" )
                compu = rdfxml.xmlrdf_get_resource_uri(component_el)
                comptitle = rdfxml.xmlrdf_get_resource_text(component_el, './/dcterms:title')
                logger.info( f"Found component {comptitle}" )
                self._components[compu] = {'name': comptitle, 'configurations': {}}
                ncomps += 1
                confu = rdfxml.xmlrdf_get_resource_uri(component_el, './/oslc_config:configurations')
                configs_xml = self.execute_get_rdf_xml( confu )
                # Each config:     <ldp:contains rdf:resource="https://jazz.ibm.com:9443/qm/oslc_config/resources/com.ibm.team.vvc.Configuration/_qT1EcEB4Eeus6Zk4qsm_Cw"/>

                for confmemberx in rdfxml.xml_find_elements(configs_xml, './/ldp:contains'):
                    thisconfu = rdfxml.xmlrdf_get_resource_uri( confmemberx )
                    try:
                        thisconfx = self.execute_get_rdf_xml(thisconfu)
                        conftitle = rdfxml.xmlrdf_get_resource_text(thisconfx, './/dcterms:title')
                        conftype = rdfxml.xmlrdf_get_resource_uri(thisconfx, './/rdf:type')
                        logger.info( f"Found config {conftitle} {conftype} {thisconfu}" )
                        self._components[compu]['configurations'][thisconfu] = {'name': conftitle, 'conftype': conftype,
                                                                                'confXml': thisconfx}
                        self._configurations[thisconfu] = self._components[compu]['configurations'][thisconfu]
                        nconfs += 1
                    except requests.exceptions.HTTPError as e:
                        pass

        # now create the "components"
        for cu, cd in self._components.items():
            cname = cd['name']
            if not self.is_optin:
                c = self
            else:
                c = self._create_component_api(cu, cname)
            c._configurations = self._components[cu]['configurations']
            self._components[cu]['component'] = c
        return (ncomps, nconfs)

    def get_local_config(self, name_or_uri):
        for cu, cd in self._configurations.items():
            logger.debug( f"{cu=} {cd=} {name_or_uri=}" )
            if cu == name_or_uri or cd['name'] == name_or_uri:
                return cu
        return None

    # load the typesystem using the OSLC shape resources
    def _load_types(self,force=False):
        logger.debug( f"load type {self=} {force=}" )

        # if already loaded, try to avoid reloading
        if self.typesystem_loaded and not force:
            return

        self.clear_typesystem()

        if self.local_config:
            # get the configuration-specific services.xml
            sx = self.get_services_xml(force=True,headers={'configuration.Context': self.local_config, 'net.jazz.jfs.owning-context': None})
        else:
            # No config - get the services.xml
            sx = self.get_services_xml(force=True)
        if sx:
            shapes_to_load = rdfxml.xml_find_elements(sx, './/oslc:resourceShape')

            pbar = tqdm.tqdm(initial=0, total=len(shapes_to_load),smoothing=1,unit=" results",desc="Loading ETM shapes")

            for el in shapes_to_load:
                self._load_type_from_resource_shape(el)
                pbar.update(1)

            pbar.close()
        else:
            raise Exception( "services xml not found!" )

        self.typesystem_loaded = True
        return None

    # pick all the attributes from a resource shape definition
    # and for enumerated attributes get all the enumeration values
    def _load_type_from_resource_shape(self, el, supershape=None):
        return self._generic_load_type_from_resource_shape(el, supershape=None)

    # return a dictionary with all local component uri as key and name as value (so two components could have the same name?)
    def get_local_component_details(self):
        results = {}
        for compuri, compdetail in self._components.items():
            results[compuri] = compdetail['name']
        return results

    def find_local_component(self, name_or_uri):
        self.load_components_and_configurations()
        for compuri, compdetail in self._components.items():
            logger.info( f"Checking {name_or_uri} {compdetail}" )
            if compuri == name_or_uri or compdetail['name'] == name_or_uri:
                return compdetail['component']
        return None

    def _create_component_api(self, component_prj_url, component_name):
        logger.info( f"CREATE QM COMPONENT {self=} {component_prj_url=} {component_name=} {self.app=} {self.is_optin=} {self.singlemode=}" )
        result = _QMComponent(component_name, component_prj_url, self.app, self.is_optin, self.singlemode, defaultinit=False, project=self)
        return result


    def is_type_uri(self, uri):
        if uri and uri.startswith(self.app.baseurl) and '/types/' in uri:
            return True
        return False

    # for OSLC query, given a type URI, return its name
    # qm-specific resolution
    def app_resolve_uri_to_name(self, uri):
        if self.is_folder_uri(uri):
            result = self.folder_uritoname_resolver(uri)
        elif self.is_resource_uri(uri):
            result = self.resource_id_from_uri(uri)
        elif self.is_type_uri(uri):
            result = self.type_name_from_uri(uri)
        else:
            result = None
        return result

    # for OSLC query, given a type URI, return the type name
    def type_name_from_uri(self, uri):
        logger.info( f"finding type name {uri}" )
        if self.is_type_uri(uri):
            try:
                # handle artifact formats (these don't have a title or label in the returned XML)
                if match:=re.search("#([a-zA-Z0-9_]+)$",uri ):
                    id = match.group(1)
                else:
                    # retrieve the definition
                    resource_xml = self.execute_get_rdf_xml(reluri=uri)
                    # check for a rdf label (used for links, maybe other things)
                    id = rdfxml.xmlrdf_get_resource_text(resource_xml,".//rdf:Property/rdfs:label") or rdfxml.xmlrdf_get_resource_text(resource_xml,".//oslc:ResourceShape/dcterms:title") or rdfxml.xmlrdf_get_resource_text(resource_xml,f'.//rdf:Description[@rdf:about="{uri}"]/rdfs:label')
                    if id is None:
                        id = f"STRANGE TYPE {uri}"
                        raise Exception( f"No type for {uri=}" )
            except requests.HTTPError as e:
                if e.response.status_code==404:
                    logger.info( f"Type {uri} doesn't exist!" )
                    raise
                else:
                    raise
            return id
        raise Exception(f"Bad type uri {uri}")

    def is_resource_uri(self, uri):
        if uri and uri.startswith(self.app.baseurl) and '/reQQsources/' in uri:
            return True
        return False

    # for OSLC query, given a resource URI, return the requirement dcterms:identifier
    def resource_id_from_uri(self, uri):
        if self.is_resource_uri(uri):
            resource_xml = self.execute_get_rdf_xml(reluri=uri)
            id = rdfxml.xmlrdf_get_resource_text(resource_xml, ".//dcterms:identifier")
            return id
        raise Exception(f"Bad resource uri {uri}")

    def is_folder_uri(self, uri):
        if uri and uri.startswith(self.app.baseurl) and '/folders/' in uri:
            return True
        return False

    def folder_nametouri_resolver(self, path_or_uri):
        logger.debug( f"Finding uri {path_or_uri}" )
        if self.is_folder_uri(path_or_uri):
            return path_or_uri
        name = self.load_folders(path_or_uri)
        if name is not None:
            return name
        if path_or_uri in self._folders:
            return self._folders[path_or_uri].folderuri
        raise Exception(f"Folder name {path_or_uri} not found")

    def folder_uritoname_resolver(self,uri):
        logger.debug( f"Finding name {uri}" )
        if not self.is_folder_uri(uri):
            raise Exception( "Folder uri isn't a uri {uri}" )
        thisfolder = self.load_folders(uri)
        if thisfolder is not None:
            return thisfolder.pathname
        logger.info( f"Folder uri {uri} not found")
        return uri

    def _do_find_config_by_name(self, name_or_uri, nowarning=False, include_workspace=True, include_snapshot=True,
                                include_changeset=True):
        if name_or_uri.startswith('http'):
            return name_or_uri
        return self.get_local_config(name_or_uri)

    def get_default_stream_name( self ):
        if self.is_optin and not self.singlemode:
            raise Exception( "Not allowed if compontn is not singlemode!" )
        for configuri,configdetails in self._configurations.items():
            if configdetails['conftype'] == 'Stream':
                return configuri
        raise Exception( "No stream found!" )

#################################################################################################

class _QMComponent(_QMProject):
    def __init__(self, name, project_uri, app, is_optin=False, singlemode=False,defaultinit=True, project=None):
        if not project:
            raise Exception( "You mist provide a project instance when creating a component" )
        super().__init__(name, project_uri, app, is_optin,singlemode,defaultinit=defaultinit)
        self.component_project = project


#################################################################################################

@utils.mixinomatic
class _QMApp(_app._App, oslcqueryapi._OSLCOperations_Mixin, _typesystem.Type_System_Mixin):
    domain = 'qm'
    project_class = _QMProject
    supports_configs = True
    supports_components = True
    supports_reportable_rest = True
    reportablerestbase='publish'
    artifactformats = [ # For RR
            '*'
            ,'collections'
            ,'comments'
            ,'comparisons'  # for 7.0.2
            ,'diff'         # for 7.0.2
            ,'linktypes'
            ,'modules'
            ,'processes'
            ,'resources'
            ,'reviews'
            ,'revisions'
            ,'screenflows'
            ,'storyboards'
            ,'terms'
            ,'text'
            ,'uisketches'
            ,'usecasediagrams'
            ,'views'
        ]
    identifier_name = 'Short ID'
    identifier_uri = 'Identifier'

    def __init__(self, server, contextroot, jts=None):
        super().__init__(server, contextroot, jts=jts)
        self.rootservices_xml = self.execute_get_xml(self.reluri('rootservices'))
        self.serviceproviders = 'oslc_qm_10:qmServiceProviders'
        self.default_query_resource = "oslc_config:Configuration"

        self.version = rdfxml.xmlrdf_get_resource_text(self.rootservices_xml,'.//oslc_rm_10:version')
        self.majorversion = rdfxml.xmlrdf_get_resource_text(self.rootservices_xml,'.//oslc_rm_10:majorVersion')
        logger.info( f"Versions {self.majorversion} {self.version}" )

    def _get_headers(self, headers=None):
        result = super()._get_headers()
        result['net.jazz.jfs.owning-context'] = self.baseurl
        if headers:
            result.update(headers)
        return result

    # load the typesystem using the OSLC shape resources listed for all the creation factories and query capabilities
    def load_types(self, force=False):
        self._load_types(force)

    # load the typesystem using the OSLC shape resources
    def _load_types(self,force=False):
        logger.debug( f"load type {self=} {force=}" )

        # if already loaded, try to avoid reloading
        if self.typesystem_loaded and not force:
            return

        self.clear_typesystem()

        # get the services.xml
        sx = self.retrieve_oslc_catalog_xml()
        if sx:
            shapes_to_load = rdfxml.xml_find_elements(sx, './/oslc:resourceShape')

            pbar = tqdm.tqdm(initial=0, total=len(shapes_to_load),smoothing=1,unit=" results",desc="Loading ETM shapes")

            for el in shapes_to_load:
                self._load_type_from_resource_shape(el)
                pbar.update(1)

            pbar.close()
        else:
            raise Exception( "services xml not found!" )

        self.typesystem_loaded = True
        return None

    # given a type URI, return its name
    def resolve_uri_to_name(self, uri, prefer_same_as=True, dontpreferhttprdfrui=True):
        logger.info( f"resolve_uri_to_name {uri=}" )
        if not uri:
            result = None
            return result
        if not uri.startswith('http://') or not uri.startswith('https://'):
        # try to remove prefix
            uri1 = rdfxml.tag_to_uri(uri,noexception=True)
            logger.debug(f"Trying to remove prefix {uri=} {uri1=}")
            if uri1 is None:
                return uri
            if uri1 != uri:
                logger.debug( f"Changed {uri} to {uri1}" )
            else:
                logger.debug( f"NOT Changed {uri} to {uri1}" )
            # use the transformed URI
            uri = uri1
        if not uri.startswith(self.baseurl):
            if self.server.jts.is_user_uri(uri):
                result = self.server.jts.user_uritoname_resolver(uri)
                logger.debug(f"returning user")
                return result
            uri1 = rdfxml.uri_to_prefixed_tag(uri,noexception=True)
            logger.debug(f"No app base URL {self.baseurl=} {uri=} {uri1=}")
            return uri1
        elif not self.is_known_uri(uri):
            if self.server.jts.is_user_uri(uri):
                result = self.server.jts.user_uritoname_resolver(uri)
            else:
                if uri.startswith( "http://" ) or uri.startswith( "https://" ):
                    uri1 = rdfxml.uri_to_prefixed_tag(uri)
                    logger.debug( f"Returning the raw URI {uri} so changed it to prefixed {uri1}" )
                    uri = uri1
                result = uri
            # ensure the result is in the types cache, in case it recurrs the result can be pulled from the cache
            self.register_name(result,uri)
        else:
            result = self.get_uri_name(uri)
        logger.info( f"Result {result=}" )
        return result
