#!/bin/bash

echo $( curl -s https://api.github.com/repos/happz/ducky/commits/master | jq '.sha' | sed 's/"//g')
