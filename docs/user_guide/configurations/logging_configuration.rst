.. _logging_configuration:

##################################
NVIDIA FLARE Logging Configuration
##################################

NVFLARE uses python logging, specifically dictConfig( configure https://docs.python.org/3/library/logging.config.html)

We provide default logging configuration files for NVFLARE sub-systems. You can overwrite these logging configurations by modifying the configuration files. 

**********************************
Logging Configuration and Features
**********************************

Logger Hierarchy
================

Formatters
==========

BaseFormatter
--------------

ColorFormatter
--------------

JsonFormatter
-------------

Filters
=======

LoggerNameFilter
----------------

Handlers
========

consoleHandler
--------------

logFileHandler
--------------

errorFileHandler
----------------

jsonFileHandler
---------------

FLFileHandler
-------------


************************************
Logging configuration files location
************************************

Startup kits log configurations
===============================

The log configuration files are located in the startup kits under the local directory.

If you search for the ``log_config.json.*`` files in the startup kits workspace, you will find the following files:

.. code-block:: shell

    find . -name "log_config.json.*"

    ./site-1/local/log_config.json.default
    ./site-2/local/log_config.json.default
    ./server1/local/log_config.json.default

The server ``log_config.json.default`` is the default logging configuration used by the FL Server and clients. To overwrite the default,
you can change ``log_config.json.default`` to ``log_config.json`` and modify the configuration.

POC log configurations
======================
Similarly, if you search the POC workspace, you will find the following:

.. code-block:: shell

    find /tmp/nvflare/poc  -name "log_config.json*"

    /tmp/nvflare/poc/server/local/log_config.json
    /tmp/nvflare/poc/site-1/local/log_config.json
    /tmp/nvflare/poc/site-2/local/log_config.json

You can directly modify ``log_config.json`` to make changes.

Simulator log configuration
===========================

Simulator logging configuration uses the default log configuration. If you want to overwrite the default configuration, you can add ``log_config.json`` to
``<simulator_workspace>/startup/log_config.json``.

For example, for hello-numpy-sag examples, the CLI command is:

.. code-block:: shell

    nvflare simulator -w /tmp/nvflare/hello-numpy-sag -n 2 -t 2 hello-world/hello-numpy-sag/jobs/hello-numpy-sag

If the workspace is ``/tmp/nvflare/hello-numpy-sag/``, then you can add log_config.json in ``/tmp/nvflare/hello-numpy-sag/startup/log_config.json`` to overwrite the default one.

Configuration logging
=====================

The default logging file-config based logging configuration is the following:

.. code-block:: shell

    [loggers]
    keys=root

    [handlers]
    keys=consoleHandler

    [formatters]
    keys=fullFormatter

    [logger_root]
    level=INFO
    handlers=consoleHandler

    [handler_consoleHandler]
    class=StreamHandler
    level=DEBUG
    formatter=fullFormatter
    args=(sys.stdout,)

    [formatter_fullFormatter]
    format=%(asctime)s - %(name)s - %(levelname)s - %(message)s

Suppose we would like to change the logging for :class:`ScatterAndGather<nvflare.app_common.workflows.scatter_and_gather.ScatterAndGather>` from to INFO to ERROR,
we can do the following:

.. code-block:: shell

    [loggers]
    keys=root, ScatterAndGather

    [handlers]
    keys=consoleHandler

    [formatters]
    keys=fullFormatter

    [logger_root]
    level=INFO
    handlers=consoleHandler

    [logger_ScatterAndGather]
    level=ERROR
    handlers=consoleHandler
    qualname=ScatterAndGather
    propagate=0

    [handler_consoleHandler]
    class=StreamHandler
    level=DEBUG
    formatter=fullFormatter
    args=(sys.stdout,)

    [formatter_fullFormatter]
    format=%(asctime)s - %(name)s - %(levelname)s - %(message)s


**************************************
Dynamic Logging Configuration Commands
**************************************


overview of two Commands

link to other place