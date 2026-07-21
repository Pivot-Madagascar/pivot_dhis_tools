# Lab Notebook : Pivot DHIS2 Tools
## Michelle Evans (mevans@pivotworks.org)

## Useful Things

`source .venv/bin/activate`: to start the python venv
`pip  install -e .`

for testing on d2 docker-test: 
```
DHIS2_PRIDEC_URL="http://localhost:8082/"
DHIS2_TOKEN="d2pat_odhYW86O8auDuQ73u4r3HElEJxMFQziM3326734980"
```

for updating releases (from main branch):

```
# update version in toml
git add pyproject.toml
git commit -m "update version to X.X.X"
git push

git tag vX.X.X
git push origin vX.X.X
#manually add relase on github
```

## 2026-07-17

Working on the calculate alerts function. I've turned it into a calc_orgUnit_alerts function that works on local data and can also fetch. This is basically done. Some tests are written for it, but need to be finalized

## 2026-07-08

To avoid rebuilding the analytics table all the time, we want to add the option for the calc_CSB_alerts to use locally available data, like from the inputs folder. See issue here: 

## 2026-06-08

I had updated the package to clear the analytics table before it gets built and it was causing errors. Now have moved to its own function and added a raise for status check.

## 2026-05-11

Created a built version of package and updated relase to v0.1.0 on github.

## 2026-5-08

Working on fixing an issue with `calc_CSB_alerts` described in this github issue: https://github.com/Pivot-Madagascar/pridec-docker/issues/6.

I added checks for empty dataFrames. I also need to actually write the pyproject file so that I can set the version of dependencies required.

**TO DO:**
- use `uv` and update pyproject file

## 2026-3-04

Added a bunch of functions that can be called by the PRIDE-C docker to help with centralizing code. I am leaving the import Pivot stuff there though because it si a bit of a pain to write as a function. Will maybe do so later.

**TO DO:**
- finish adding functions
- write tests
- update to use logging and not print
- chagne how functions are defined so teh class of arguments is set [https://github.com/google/styleguide/blob/gh-pages/pyguide.md#383-functions-and-methods for docstrings too]

## 2026-02-26

Beginning to migrate our most commonly used functions over to this library. This includes:

- ~~deleting a range of data [pridec_gee]~~
- ~~fetching PRIDE-C specific data (climate, historical disease) [pridec-docker]~~
- ~~posting new dataElements [pridec_gee]~~
- ~~estimating CSB vigilance [create-dev-dhis2]~~
- documentation on Pivot specific codes (like which OU level means what)
- ~~importing data from Pivot instance into PRIDE-C instance (COM and CSB) [pridec-docker]~~: done in docker still
- ~~launching analytics table [pridec-docker]~~
- ~~creating a pride-c dataStore update [pridec-docker]~~
- create PRIDE-C metadata [create-dev-dhis2]
- get dataElement metadata based on code search [pridec_gee]

The PRIDE-C specific thigns may do better in their own library, but they will be here for now