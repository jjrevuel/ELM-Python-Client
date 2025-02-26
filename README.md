# Python client for IBM Enterprise Lifecycle Management applications


 Python client for IBM Enterprise Lifecycle Management applications


 (c) Copyright 2021- IBM Inc. All rights reserved
 SPDX-License-Identifier: MIT

 version="0.2.8"


Introduction
============

The aim of this code is to provide a Python client for the IBM Enterprise Lifecycle Management (ELM) applications.

IMPORTANT NOTES:
* This code is not developed, delivered or supported in any way as part of the IBM ELM applications
* This code is not supported other than by the efforts of the author and contributors in this github repository
* This code is not intended to be complete/comprehensive - it provides functionality needed by the examples and little else.

Included in this package are a few examples using `elmclient` which are reasonably functional:
* OSLC Query able to work with DOORS Next (DN), Engineering Test Management (ETM), Engineering Workflow Management (EWM) and Global Configuration management (GCM)
* ReqIF import/export for DOORS Next
* Reportable REST for DOORS Next - very basic!

There are links to these examples below.

Installation
============

Requirements:

This version has been tested with:
* Python 3.9.1 x64 on Windows 10 x64**.
* Python 3.9.6 x64 on CentOS (Redhat) 8.4

The only version constraint of the requirements is on Windows that requests==2.24.0 and urllib3==1.25.11 - On Windows there seems to be a problem with requests>=2.25.0 (latest is 2.26.0) when using Fiddler proxy on port 8888.

The move to Python 3.9 was relatively recent - this code may work with 3.8.x and possibly earlier versions. Trying to install with Python 3.10 using `pip` failed when getting `lxml` - there may be other problems as didn't get past this.

The content on github is at https://github.com/IBM/ELM-Python-Client

NOTE: the python package installed is call `elmclient`

FIRST option is to install from the github.com zip:

Download the github zip:

* wget https://github.com/IBM/ELM-Python-Client/archive/refs/heads/master.zip

Unzip to its own folder and open a command prompt in that folder.

Either, install using:

```
python setup.py install
```

This adds the example commands (e.g. `oslcquery`) to the Python Scripts folder - if this folder is in the path you can use the command from anywhere.


Or, if you want to run from source because you want to modify the code then download the github zip then you can extract it to a directory of your choice and install as an editable package by opening a command prompt in the directory and using the command:

```
pip install -e .
```

This installs the elmclient and puts example commands into your scripts so a) they can be run simply by typing the command, e.g. `oslcquery` and b) as you edit the source code these commands automatically use the latest code.


SECOND option its to install from pypi using pip:

The package is available from pypi it will be installed using `pip` (NOTE there's isn't a -e for editable install option when using `pip` to install from `pypi`):

```
pip install elmclient
```

This will install the provided example commands such as `oslcquery`, `batchquery`, `reqif_io`, etc. to the python scripts folder; for ease of use, when installing Python make sure this is in your path.


Coding using the elmclient
==========================

The basis of using the elmclient is to first create a "server", then add the needed application(s) to it - typically just one application such as rm, or perhaps more applications such as rm and gc.

Then you can use the API functions to find projects, components, configurations, etc.

The DN reportable REST example provides a simple functional example with hard-coded values for the project, configuration and the artifact ID to be queried. This is the easy way to get into using elmclient - by modifying this example.

The other examples add fairly complex details around the use of elmclient to provide a commandline interface and should provide again a starting point for further development.


Authentication (in httpops.py)
==============================

The auth code works with form authentication using Liberty in local user registry, LDAP and OIDC (Jazz Authorisation Server) modes. Other modes haven't been tested. You'll have to provide a username and password. The examples `oslcquery` and `reqif_io` layer methods on top of this to allow saving obfuscated credentials to a file so you don't have to provide these on the commandline every time. See the code for these examples.


Handling different context roots
================================

It's possible to install the ELM applications to run on non-standard context roots like /rm1 for DOORS Next, or /scm for EWM. This is handled in `elmclient` using APPSTRINGs. These specify the domain of an application using rm, jts, gc, ccm, qm, and the context root as a string without the leading /. So for example /rm1 would be specified as `rm:rm1`, or /scm would be specified as `ccm:scm`.

For example, if your DN is on /rm then just specify `rm`. Or, if it's on /rm23 then specify `rm:rm23`.

If more than one application is needed then use a comma separate list (without spaces). The main application is specified first, but if jts is also on /jts1 then your APPSTRING could be `rm:rm1,jts:jts1`.


Example code provided
=====================

These examples drove the evolution of `elmclient`:

* OSLC Query - read more [here](elmclient/examples/OSLCQUERY.md) - this is the largest example by quite a margin. It enables commandline export to CSV from the supported applications using an abstract syntax for OSLC Query.
* ReqIF import/export - read more [here](elmclient/examples/REQIF_IO.md) - this allows limited CRUD of reqif definitions in DOORS Next, performing multiple reqif export using a definition, and multiple reqif import
* DOORS Next Reportable REST - read more [here](elmclient/examples/DN_REPREST.md) - this is a very simple example of using `elmclient` to access the DOORS Next Reportable REST API


Reporting issues, and contributing
==================================

If you find a problem with elmclient you can report it on the github issues; note this is just for elmclient code. All other issues will likely be closed immediately.

You can do a pull request to propose updates - there's no guarantee of if/when/how these will be merged.

