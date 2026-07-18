#!/bin/bash
grep -R -n "len(df" modules src ui tests && \
grep -R -n "shape\[0\]" modules src ui tests && \
grep -R -n "len(.*\.columns" modules src ui tests
