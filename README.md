# Smart Symmetry

## DISCLAIMER:
**This is vibe-coded AI slop.** I am not a programmer. I can't guarantee that I will be able to maintain this add-on as Blender updates their Python API, nor can I vouch for the quality of the code. It is something I wanted for personal use, and does the job I wanted it for. Use at your own risk. 

## Why does this exist?
Most sculpting programs default with X symmetry enabled. Blender doesn't in a general use project, because it shares symmetry settings between all of its modes. I like sculpting with X symmetry on most of the time. I hate editing with X symmetry on most of the time. I got sick of forgetting to turn it on in sculpt mode, then forgetting to turn it off in edit mode. I also prefer using the "Fix Poles" option for remeshing in sculpt mode. Blender defaults with it off because it's more performance intensive. I got sick of having it manually turn it on all the time. 

## What does it do?

This add on allows you to set a default symmetry setting on each axis in each mode, and remembers what your symmetry is set to independently in each mode. New objects have X symmetry enabled by default in sculpt mode, but will not have symmetry enabled in other modes. Any changes you make to symmetry settings will be remembered independently in each mode, even when reopening a project. 

By default, Vertex Paint and Texture Paint use Sculpt Mode's symmetry instead of their own, so the three share one setting per object (and start with X symmetry like Sculpt Mode does). Changing it in any of the three changes it for all of them. Edit Mode and Weight Paint always keep their own. Turn this off if you want Vertex Paint and Texture Paint to remember their own symmetry separately.

By default, new objects will have the "Fix Poles" remeshing option switched on when first entering sculpt mode. 

By default, armatures added to the project automatically have "In Front" turned on and are set to "Display As: Wire", which keeps the bone shapes but makes them easier to see through. The two are separate toggles. Armatures already in the project are left alone.

By default, Armature Edit Mode has its own pivot point. The first time an armature enters Edit Mode the pivot is set to "Active Element"; after that each armature remembers the pivot it last used there, and the pivot you were using before is put back when you leave Edit Mode.

All of the settings can be toggled on/off in the add-on preferences panel. 

<img width="1061" height="1024" alt="smartsym" src="https://github.com/user-attachments/assets/cf4bf8c2-c081-4dc8-ba58-43c168b8d744" />
