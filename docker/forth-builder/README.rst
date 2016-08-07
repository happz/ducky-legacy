"Build FORTH kernel" docker image
=================================

Usage
-----

.. code-block:: bash

  cd docker/forth-builder
  docker build -t ducky-forth-builder .
  docker-compose up --force-recreate
  ls -alh /tmp/ducky-forth.tar.gz
