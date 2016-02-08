#!/bin/bash

commit="$(curl -s https://api.github.com/repos/happz/ducky/commits/master)"

HASH=$(echo $commit | jq '.sha' | sed 's/"//g')
DATE=$(echo $commit | jq '.commit.author.date' | tr -d '\n"Z' | tr -d '-' | tr 'T' '-' | tr -d ':')

echo "$HASH-$DATE"
