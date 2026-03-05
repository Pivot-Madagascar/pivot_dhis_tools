# Lab Notebook : Pivot DHIS2 Tools
## Michelle Evans (mevans@pivotworks.org)

## Useful Things

`source .venv/bin/activate`: to start the python venv 

for testing on d2 docker-test: 
```
DHIS2_PRIDEC_URL="http://localhost:8082/"
DHIS2_TOKEN="d2pat_odhYW86O8auDuQ73u4r3HElEJxMFQziM3326734980"
```

for testing on DHIS2 play instance:

## 2026-3-04

Added a bunch of functions that can be called by the PRIDE-C docker to help with centralizing code. I am leaving the import Pivot stuff there though because it si a bit of a pain to write as a function. Will maybe do so later.

**TO DO:**
- finish adding functions
- write tests
- update to use loggin and not print

## 2026-02-26

Beginning to migrate our most commonly used functions over to this library. This includes:

- ~~deleting a range of data [pridec_gee]~~
- ~~fetching PRIDE-C specific data (climate, historical disease) [pridec-docker]~~
- ~~posting new dataElements [pridec_gee]~~
- estimating CSB vigilance [create-dev-dhis2]
- documentation on Pivot specific codes (like which OU level means what)
- ~~importing data from Pivot instance into PRIDE-C instance (COM and CSB) [pridec-docker]~~: done in docker still
- ~~launching analytics table [pridec-docker]~~
- ~~creating a pride-c dataStore update [pridec-docker]~~
- create PRIDE-C metadata [create-dev-dhis2]
- get dataElement metadata based on code search [pridec_gee]

The PRIDE-C specific thigns may do better in their own library, but they will be here for now