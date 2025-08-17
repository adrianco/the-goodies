
# User generated content samples for testing

PAR-42.jpeg - photo of Mitsubishi thermostat
PAR-42MAAUB_Instrauction Bookpdf - User manual for thermostat
PVFY-Blower.jpeg - photo of installed air handler blower unit
PVFY-Serial_Number.jpeg - photo of serial number plate for air handler

## User provided notes
This thermostat is in the kitchen, it controls the air blower that heats and cools the kitchen, dining room, living room, bar and kitchen bathroom. The air blower is in a closet in the garage. The thermostat can be remotely controlled using the Mitsubishi Comfort app on iPhone or iPad.

## Feature enhancements for UGC
Store provided user notes in existing NOTES entity

Add new capability to store original pdf manual and photos as binary large objects (BLOBs) in entities, and sync to/from server

Summarize pdf manual and create MANUAL entity that refers to original pdf BLOB

Store photos as BLOBs and link them to 

Create new entity type for APP with name, icon and URL scheme, link homekit based entities to the Apple Homekit app, and link Mitsubishi thermostat entity to the Comfort app.

Update demo house data to include these new entities and a Mitsubishi thermostat

Create and run tests for all the new functionality

