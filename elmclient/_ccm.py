##
## © Copyright 2021- IBM Inc. All rights reserved
# SPDX-License-Identifier: MIT
##


import logging

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

class _CCMProject(_project._Project):
    def __init__(self, name, project_uri, app, is_optin,singlemode):
        super().__init__(name, project_uri, app, is_optin,singlemode)
        self.default_query_resource = 'oslc_cm1:ChangeRequest'

    # for CCM, load the typesystem using all resourceshapes in the services xml
    def _load_types(self,force=False):
        if self.typesystem_loaded and not force:
            return
        self.clear_typesystem()

        sx = self.get_services_xml()

        if sx:
            shapes_to_load = rdfxml.xml_find_elements(sx, './/oslc:resourceShape')

            pbar = tqdm.tqdm(initial=0, total=len(shapes_to_load),smoothing=1,unit=" results",desc="Loading EWM shapes")

            for el in shapes_to_load:
                self._load_type_from_resource_shape(el)
                pbar.update(1)

            pbar.close()

            return
        self.typesystem_loaded = True
        return None

    # pick all the attributes from a resource shape definition
    # and for enumerated attributes get all the enumeration values
    def _load_type_from_resource_shape(self, el, supershape=None):
        uri = el.get("{%s}resource" % rdfxml.RDF_DEFAULT_PREFIX["rdf"])
        logger.info( f"_load_type_from_resource_shape {el=} {uri=}" )
        try:
            if not self.is_known_shape_uri(uri):
                logger.info( f"Starting shape {uri} =======================================" )
                logger.debug( f"Getting {uri}" )
                shapedef = self._get_typeuri_rdf(uri)
                name = rdfxml.xml_find_element(shapedef, f".//rdf:Description[@rdf:about='{uri}']/dcterms:title").text
                self.register_shape( name, uri )
                logger.info( f"Opening shape {name} {uri}" )
            else:
                logger.info( "ENDED" )
                return
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug("Failed because type not found - ignoring!", e)
                return
            else:
                raise
                # find the   <rdf:Description rdf:about="https://jazz.net/jazz03/oslc/context/_s_M8MMFIEdumDPUtna_vLA/shapes/workitems/defect">
        # go through all contained    <oslc:property rdf:resource="https://jazz.net/jazz03/oslc/context/_s_M8MMFIEdumDPUtna_vLA/shapes/workitems/defect/property/howfound"/>
        # for each find the   <rdf:Description rdf:about="https://jazz.net/jazz03/oslc/context/_s_M8MMFIEdumDPUtna_vLA/shapes/workitems/defect/property/howfound">
        # get its nested <dcterms:title rdf:parseType="Literal">How Found</dcterms:title>
        # save as defn.property
        # Either
        #   check for contained     <oslc:allowedValues rdf:resource="https://jazz.net/jazz03/oslc/context/_s_M8MMFIEdumDPUtna_vLA/shapes/workitems/defect/property/howfound/allowedValues"/>
        #   find   <rdf:Description rdf:about="https://jazz.net/jazz03/oslc/context/_s_M8MMFIEdumDPUtna_vLA/shapes/workitems/defect/property/howfound/allowedValues">
        #   each contained enum value <oslc:allowedValue rdf:resource="https://jazz.net/jazz03/oslc/enumerations/_s_M8MMFIEdumDPUtna_vLA/howfound/howfound.literal.l20"/>
        #   use the last \w+ of the rdf:resource URL as the name of the enum value
        # OR
        #     <oslc:range rdf:resource="https://jazz.net/jazz03/oslc/enumerations/_s_M8MMFIEdumDPUtna_vLA/OS"/>
        #     lists the enumeration values somehow
        # leave enumeration values to be resolved only when the type is used so we don't spend forever retrieving unused definitions
        n = 0
        # find the list of attributes
        thisshapedef = rdfxml.xml_find_element( shapedef,f'.//rdf:Description[@rdf:about="{uri}"]' )
        if thisshapedef is None:
            raise Exception( f"Shape definition for {uri} not found!" )

        title = rdfxml.xmlrdf_get_resource_text(thisshapedef,'./dcterms:title')

        # scan the attributes
        for propel in rdfxml.xml_find_elements( thisshapedef,'./oslc:property' ):
            propuri = rdfxml.xmlrdf_get_resource_uri(propel)
            real_propel = rdfxml.xml_find_element(shapedef, f'.//rdf:Description[@rdf:about="{propuri}"]')
            property_title = rdfxml.xml_find_element(real_propel, './dcterms:title').text
#            property_uri = rdfxml.xmlrdf_get_resource_uri(real_propel,'./oslc:valueShape')
            proptype = rdfxml.xmlrdf_get_resource_uri(real_propel,'./oslc:valueType' )
            property_definition_uri = rdfxml.xmlrdf_get_resource_uri(real_propel,'./oslc:propertyDefinition' )

            if self.is_known_property_uri( propuri ):
                logger.debug( f"ALREADY KNOWN" )
                continue

            # EWM seems to not infrequently have repeated identical property titles on a shape, so let's create an alternative name that can be used to disambiguate
            # (at least these don't have duplicates AFAICT)
            altname  = propuri[propuri.rfind("/")+1:]
            if len(altname)==0 or altname==property_title:
                altname = None

            logger.info( f"Defining property {title}.{property_title} {altname=} {propuri=} +++++++++++++++++++++++++++++++++++++++" )
            self.register_property(property_title,propuri, shape_uri=uri, altname=altname,property_definition_uri=property_definition_uri)

            allowedvaluesu = rdfxml.xmlrdf_get_resource_uri(real_propel, ".//oslc:allowedValues" )
            if allowedvaluesu is not None:
                # get the enumeration definitions
                thisenumrangex = rdfxml.xml_find_element( shapedef,f'.//rdf:Description[@rdf:about="{allowedvaluesu}"]' )
                # retrieve each definition
                nvals = 0
                for enumvalx in rdfxml.xml_find_elements( thisenumrangex,'.//oslc:allowedValue'):
                    logger.debug( f"{enumvalx=}" )
                    enum_uri = rdfxml.xmlrdf_get_resource_uri(enumvalx)
                    logger.debug( f"{enum_uri=}" )
                    nvals += 1
                    if not self.is_known_enum_uri( enum_uri ):
                        # retrieve it and save the enumeration name and uri in types cache
                        try:
                            enumx = self._get_typeuri_rdf(enum_uri)
                            enum_value_name = rdfxml.xmlrdf_get_resource_uri(enumx, './/rdf:Description/dcterms:title')
                            enum_id = rdfxml.xmlrdf_get_resource_uri(enumx, './/rdf:Description/dcterms:identifier' )
                        except requests.HTTPError as e:
                            if e.response.status_code in [403,404,406]:
                                logger.debug( f"Type {uri} doesn't exist!" )
                            else:
                                raise
                            logger.info( f"No title for {enum_uri}" )
                            enum_id=None
                            enum_value_name = None
                        if enum_value_name is None:
                            enum_value_name = enum_uri

                        if enumx is None:
                            logger.info( "Enumx is None - skipping the type" )
                            continue

                        logger.info( f"defining enum value {enum_value_name=} {enum_id=} {enum_uri=}" )
                        if not self.app.server.jts.is_user_uri(uri):
                            self.register_enum( enum_value_name, enum_uri, id=enum_id, property_uri=propuri )
                        else:
                            logger.debug( f"Not registering enum value for user {uri}" )
                        # (only) the various work item types have a 'category' - this can be used to filter for them on property rtc_cm:type
                        category = rdfxml.xmlrdf_get_resource_text(enumx, './/rdf:Description/rtc_cm:category' )
                        if category is not None:
                            # register this shape as an rtc_cm:type enum
                            logger.info( f"Defining category rtc_cm:type {enum_value_name} {enum_id} {category} {enum_uri}" )
                            # ensure the rtc_cm:type property is defined (but don't overwrite existing definition)
                            self.register_property( 'rtc_cm:type', 'rtc_cm:type', do_not_overwrite=True )
                            # add the shape to it using the shape's URI as an enum URI
                            # NOTE the use of the id - this id is used when comparing values with rtc_cm_type to see workaround https://jazz.net/forum/questions/86619/oslc-20-query-with-oslcwhere-parameter-dctermstype-returns-400-unknown-attribute-id
                            self.register_enum( enum_value_name, enum_uri, 'rtc_cm:type',id=enum_id )

                if nvals==0:
                    raise Exception( f"Enumeration {propuri} with no values loaded" )
        return n


    # for OSLC query, given a type URI, return its name
    # ccm-specific resolution
    def app_resolve_uri_to_name(self, uri):
        if self.is_resource_uri(uri):
            result = self.resource_id_from_uri(uri)
        elif self.is_type_uri(uri):
            result = self.type_name_from_uri(uri)
        else:
            result = None
        return result

    def get_missing_uri_title( self,uri):
        id = None
        if uri.startswith( self.app.baseurl ):
            try:
                resource_xml = self.execute_get_rdf_xml(reluri=uri)
                id = rdfxml.xmlrdf_get_resource_text(resource_xml, ".//dcterms:title")
            except ET.XMLSyntaxError as e:
                logger.debug( f"Type {uri} doesn't exist (not XML)!" )
            except requests.HTTPError as e:
                if e.response.status_code==404 or e.response.status_code==406:
                    logger.debug( f"Type {uri} doesn't exist!" )
                else:
                    raise
        if id is None and ( uri.startswith( "http://" ) or uri.startswith( "https://" ) ):
            uri1 = rdfxml.uri_to_prefixed_tag(uri)
            logger.debug( f"Returning the raw URI {uri} so changed it to prefixed {uri1}" )
            id = uri1

        logger.debug( f"gmut {id=}" )

        return id

    # for OSLC query, given a type URI, return the type name
    def type_name_from_uri(self, uri):
        if self.is_type_uri(uri):
            try:
                resource_xml = self.execute_get_rdf_xml(reluri=uri)
                id = rdfxml.xmlrdf_get_resource_text(resource_xml, ".//dcterms:identifier")
            except requests.HTTPError as e:
                if e.response.status_code==404 or e.response.status_code==406:
                    logger.debug( f"Type {uri} doesn't exist!" )
                else:
                    raise
                id = uri
            return id
        raise Exception(f"Bad type uri {uri}")

    # for OSLC query, given a resource URI, return identifier - for CCM this is the last part of the URI
    def resource_id_from_uri(self, uri):
        if self.is_resource_uri(uri):
            id = uri[uri.rfind("/")+1:]
            return id
        raise Exception(f"Bad resource uri {uri}")

    def is_resource_uri(self, uri):
        if uri and uri.startswith(self.app.baseurl) and '/resources/' in uri:
            return True
        return False

    def is_type_uri(self, uri):
        if uri and uri.startswith(self.app.baseurl) and '/oslc/context/' in uri:
            return True
        return False

#################################################################################################

@utils.mixinomatic
class _CCMApp(_app._App, _typesystem.No_Type_System_Mixin):
    domain = 'ccm'
    project_class = _CCMProject
    supports_configs = False
    supports_components = False
    reportablerestbase='rpt/repository'
    supports_reportable_rest = True
    artifact_formats = [ # For RR
        'foundation'
        ,'scm'
        ,'build'
        ,'apt'
        ,'workitem'
        ]
    identifier_name = 'id'
    identifier_uri = 'dcterms:identifier'

    def __init__(self, server, contextroot, jts=None):
        super().__init__(server, contextroot, jts=jts)
        self.rootservices_xml = self.execute_get_xml(self.reluri('rootservices'))
        self.serviceproviders = 'oslc_cm:cmServiceProviders'
        self.reportablerestbase = self.contextroot+'/rpt/repository'

    def _get_headers(self, headers=None):
        result = super()._get_headers()
        result['net.jazz.jfs.owning-context'] = self.baseurl
        result['OSLC-Core-Version'] = '2.0'
        if headers:
            result.update(headers)
        return result

