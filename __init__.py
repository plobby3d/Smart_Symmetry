# Smart Symmetry -- a Blender extension. Name, version and description live
# in blender_manifest.toml.

import bpy
from bpy.app.handlers import persistent

# ---------------------------------------------------------------------------
# Why this exists
# ---------------------------------------------------------------------------
# In current Blender, the X/Y/Z mirror buttons shown in Edit Mesh, Sculpt,
# and Vertex/Weight/Texture Paint are not separate settings -- they all read
# and write ONE shared property: Object.use_mesh_mirror_x/y/z. Changing the
# symmetry in one mode therefore changes it in every other mode.
#
# This addon keeps its own small per-object memory of the XYZ symmetry used
# in each mode. While an object is in a mode, any change to the shared
# property is saved to that mode's memory. When a mode is entered, that
# mode's memory is written back to the shared property. The first time an
# object enters a mode (nothing remembered yet), the default for that mode
# from the addon's preferences is used instead.
#
# Each object also records which mode its shared property currently holds
# the value for. Comparing that with the mode the object is actually in is
# how a mode change is noticed, including one produced by undo.
#
# The memory is stored on each object, so it is saved in the .blend file and
# comes back when the project is reopened (unless "Reapply Defaults When
# Opening Existing Project" is on, which clears it on load).
#
# Blender only allows X symmetry in Weight Paint (Y and Z are read-only
# there), so axes Blender won't let us change in a mode are left alone.

# Object.mode value -> key used for storage and preference names.
MODE_KEYS = {
    'EDIT': 'edit',
    'SCULPT': 'sculpt',
    'VERTEX_PAINT': 'vertex_paint',
    'WEIGHT_PAINT': 'weight_paint',
    'TEXTURE_PAINT': 'texture_paint',
}

MODE_LABELS = {
    'edit': "Edit Mode",
    'sculpt': "Sculpt Mode",
    'vertex_paint': "Vertex Paint",
    'texture_paint': "Texture Paint",
    'weight_paint': "Weight Paint",
}

# Used only if the addon's preferences can't be read.
FALLBACK_DEFAULTS = {
    'edit': (False, False, False),
    'sculpt': (True, False, False),
    'vertex_paint': (False, False, False),
    'weight_paint': (False, False, False),
    'texture_paint': (False, False, False),
}

# Weight Paint only supports X symmetry, so only X is offered for it.
MODE_AXES = {
    'weight_paint': "X",
}

# Storage key -> Object.mode value.
KEY_MODES = {key: mode for mode, key in MODE_KEYS.items()}

# Modes that use Sculpt Mode's symmetry (its storage key and its default)
# instead of their own while "Vertex and Texture Paint Use Sculpt Mode's
# Symmetry" is on. Their own remembered values are kept, untouched, for when
# the option is turned off.
SCULPT_SHARED_KEYS = ('vertex_paint', 'texture_paint')

# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def _symmetry_option_changed(_self, _context):
    # Changing a preference doesn't cause a scene update, so apply it to the
    # active object now rather than at whatever happens to update next.
    _apply_current_mode()


class SmartSymmetryPreferences(bpy.types.AddonPreferences):
    # For an extension this is the package name Blender installs it under
    # (bl_ext.<repository>.smart_symmetry), which __package__ resolves to.
    bl_idname = __package__

    remember_symmetry: bpy.props.BoolProperty(
        name="Remember Symmetry per Mode",
        description=(
            "Remember each object's XYZ symmetry separately for Edit, Sculpt, "
            "Vertex Paint, Texture Paint and Weight Paint, and reapply it "
            "when that mode is entered (Vertex and Texture Paint can share "
            "Sculpt Mode's instead, see the next option). When off, the "
            "addon doesn't change symmetry (Fix Poles is unaffected)"
        ),
        default=True,
        update=_symmetry_option_changed,
    )
    share_sculpt_symmetry: bpy.props.BoolProperty(
        name="Vertex and Texture Paint Use Sculpt Mode's Symmetry",
        description=(
            "Sculpt Mode, Vertex Paint and Texture Paint share one symmetry "
            "setting per object, so changing it in any of them changes it "
            "for all three. When off, each of the three remembers its own. "
            "Edit Mode and Weight Paint always keep their own"
        ),
        default=True,
        update=_symmetry_option_changed,
    )
    apply_defaults_on_load: bpy.props.BoolProperty(
        name="Reapply Defaults When Opening Existing Project",
        description=(
            "When a project is opened, discard the symmetry remembered in "
            "that file and start every mode from the defaults below. When "
            "off, a project keeps the symmetry it was saved with and the "
            "defaults are only used for modes an object hasn't been in yet"
        ),
        default=False,
    )
    default_fix_poles: bpy.props.BoolProperty(
        name="Default Fix Poles ON (first Sculpt Mode entry)",
        description="The first time a mesh enters Sculpt Mode, turn on Voxel Remesh's Fix Poles option",
        default=True,
    )
    armature_in_front: bpy.props.BoolProperty(
        name="In Front",
        description=(
            "When an armature is added to the project (created, appended or "
            "imported), turn on its In Front option so it shows through "
            "other objects. Armatures already in the project are left alone, "
            "and you can still change an armature's display afterwards"
        ),
        default=True,
    )
    armature_display_wire: bpy.props.BoolProperty(
        name="Display As Wire",
        description=(
            "When an armature is added to the project (created, appended or "
            "imported), set its object Display As to Wire, so the bones keep "
            "their shape but are drawn as see-through wireframe. Armatures "
            "already in the project are left alone, and you can still change "
            "an armature's display afterwards"
        ),
        default=True,
    )

    armature_edit_pivot: bpy.props.BoolProperty(
        name="Default Pivot to Active Element (first Armature Edit Mode entry)",
        description=(
            "Give Armature Edit Mode its own Pivot Point, separate from "
            "everything else. The first time an armature enters Edit Mode "
            "the pivot is set to Active Element; after that each armature "
            "remembers the pivot it last used there. Leaving Edit Mode puts "
            "back the pivot that was in use before. When off, the addon "
            "doesn't change the pivot point"
        ),
        default=True,
    )

    default_edit_symmetry: bpy.props.BoolVectorProperty(
        name="Edit Mode", size=3, subtype='XYZ', default=FALLBACK_DEFAULTS['edit'],
        description="Default XYZ symmetry for Edit Mode",
    )
    default_sculpt_symmetry: bpy.props.BoolVectorProperty(
        name="Sculpt Mode", size=3, subtype='XYZ', default=FALLBACK_DEFAULTS['sculpt'],
        description="Default XYZ symmetry for Sculpt Mode",
    )
    default_vertex_paint_symmetry: bpy.props.BoolVectorProperty(
        name="Vertex Paint", size=3, subtype='XYZ', default=FALLBACK_DEFAULTS['vertex_paint'],
        description="Default XYZ symmetry for Vertex Paint",
    )
    default_weight_paint_symmetry: bpy.props.BoolVectorProperty(
        name="Weight Paint", size=3, subtype='XYZ', default=FALLBACK_DEFAULTS['weight_paint'],
        description="Default X symmetry for Weight Paint (Blender only allows X there)",
    )
    default_texture_paint_symmetry: bpy.props.BoolVectorProperty(
        name="Texture Paint", size=3, subtype='XYZ', default=FALLBACK_DEFAULTS['texture_paint'],
        description="Default XYZ symmetry for Texture Paint",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "remember_symmetry")
        row = layout.row()
        row.enabled = self.remember_symmetry
        row.prop(self, "share_sculpt_symmetry")
        layout.prop(self, "apply_defaults_on_load")

        box = layout.box()
        box.label(text="Default Symmetry")
        col = box.column(align=True)
        for key, label in MODE_LABELS.items():
            split = col.split(factor=0.3, align=True)
            # Greyed out while the mode is using Sculpt Mode's symmetry.
            split.enabled = not (self.share_sculpt_symmetry and key in SCULPT_SHARED_KEYS)
            split.label(text=label)
            row = split.row(align=True)
            for index, axis in enumerate(MODE_AXES.get(key, "XYZ")):
                row.prop(self, "default_%s_symmetry" % key, index=index, text=axis, toggle=True)

        layout.prop(self, "default_fix_poles")

        box = layout.box()
        box.label(text="Default Display for New Armatures")
        col = box.column(align=True)
        col.prop(self, "armature_in_front")
        col.prop(self, "armature_display_wire")

        layout.prop(self, "armature_edit_pivot")


def _get_prefs():
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        return None


def _default_axes(key):
    prefs = _get_prefs()
    if prefs is None:
        return FALLBACK_DEFAULTS[key]
    return tuple(getattr(prefs, "default_%s_symmetry" % key))


# ---------------------------------------------------------------------------
# Per-object / per-mesh storage
# ---------------------------------------------------------------------------

class ModeSymmetryState(bpy.types.PropertyGroup):
    # False until this object has entered the mode once (or after remembered
    # symmetry is cleared on project load). While False, the preference
    # default for the mode is used the next time the mode is entered.
    initialized: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    axes: bpy.props.BoolVectorProperty(size=3, default=(False, False, False))


class ObjectSymmetryMemory(bpy.types.PropertyGroup):
    edit: bpy.props.PointerProperty(type=ModeSymmetryState)
    sculpt: bpy.props.PointerProperty(type=ModeSymmetryState)
    vertex_paint: bpy.props.PointerProperty(type=ModeSymmetryState)
    weight_paint: bpy.props.PointerProperty(type=ModeSymmetryState)
    texture_paint: bpy.props.PointerProperty(type=ModeSymmetryState)
    # Which mode (a MODE_KEYS value, or '' for none) the object's shared
    # X/Y/Z symmetry currently holds the value for. Undo restores this
    # together with the X/Y/Z values, which is what lets the addon tell,
    # after an undo, that they are a different mode's and need swapping.
    axes_mode: bpy.props.StringProperty(default='', options={'HIDDEN'})


class MeshFixPolesInit(bpy.types.PropertyGroup):
    initialized: bpy.props.BoolProperty(default=False, options={'HIDDEN'})


class ArmaturePivotState(bpy.types.PropertyGroup):
    # Stored on each armature object: the pivot point it last used in Edit
    # Mode. False `initialized` means it hasn't entered Edit Mode yet (or the
    # memory was cleared on project load), so Active Element is used.
    initialized: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    pivot: bpy.props.StringProperty(default='ACTIVE_ELEMENT')


class ScenePivotRestore(bpy.types.PropertyGroup):
    # Stored on the scene (the pivot point is a scene setting): a copy, for
    # the .blend file, of the pivot that was in use before Armature Edit Mode
    # was entered. `stored` is only True while in Armature Edit Mode. See the
    # "Armature Edit Mode pivot point" section for why it's only a copy.
    stored: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    outside: bpy.props.StringProperty(default='MEDIAN_POINT')


class ArmatureDisplayInit(bpy.types.PropertyGroup):
    # True once the addon has set this armature's display. Stored on the
    # object so that undoing back to before it was set reverts this too, and
    # the display is then applied again.
    initialized: bpy.props.BoolProperty(default=False, options={'HIDDEN'})


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _ensure_fix_poles_default(obj):
    """The first time this mesh enters Sculpt Mode, default Fix Poles on."""
    if obj is None or obj.type != 'MESH':
        return
    mesh = obj.data
    init = mesh.fix_poles_init
    if not init.initialized:
        mesh.use_remesh_fix_poles = True
        init.initialized = True


def _read_axes(obj):
    if hasattr(obj, "use_mesh_mirror_x"):
        return (obj.use_mesh_mirror_x, obj.use_mesh_mirror_y, obj.use_mesh_mirror_z)
    mesh = obj.data
    return (mesh.use_mirror_x, mesh.use_mirror_y, mesh.use_mirror_z)


def _editable_axes(obj):
    """Which of X/Y/Z Blender currently lets us change on this object (e.g.
    Weight Paint only allows X, so Y and Z are read-only there)."""
    if not hasattr(obj, "use_mesh_mirror_x"):
        return (True, True, True)
    return tuple(not obj.is_property_readonly("use_mesh_mirror_" + axis) for axis in "xyz")


def _write_axes(obj, axes):
    editable = _editable_axes(obj)
    current = _read_axes(obj)
    for index, axis in enumerate("xyz"):
        if not editable[index] or current[index] == axes[index]:
            continue
        if hasattr(obj, "use_mesh_mirror_x"):
            setattr(obj, "use_mesh_mirror_" + axis, axes[index])
        else:
            setattr(obj.data, "use_mirror_" + axis, axes[index])


def _remembering(prefs):
    return prefs is None or prefs.remember_symmetry


def _storage_key(mode, prefs):
    """The key an object's symmetry is remembered under while in `mode`
    ('' for modes without symmetry, such as Object Mode)."""
    key = MODE_KEYS.get(mode, '')
    if key in SCULPT_SHARED_KEYS and (prefs is None or prefs.share_sculpt_symmetry):
        return 'sculpt'
    return key


def _store_axes(obj, key, editable):
    """Save the object's current symmetry as the remembered value for the
    mode `key`. Axes that weren't editable in that mode keep their remembered
    value, and nothing is saved for a mode this object hasn't been
    initialized for."""
    state = getattr(obj.symmetry_memory, key) if key in KEY_MODES else None
    if state is None or not state.initialized:
        return
    current = _read_axes(obj)
    merged = tuple(current[i] if editable[i] else state.axes[i] for i in range(3))
    if tuple(state.axes) != merged:
        state.axes = merged


def _editable_in(obj, key):
    """Which axes were editable while `obj` was in the mode `key`, now that
    it has left it. Uses what was seen on the last update if that was this
    object in that mode, otherwise what the mode is known to allow."""
    if _last_state == (obj.name, KEY_MODES.get(key)):
        return _last_editable
    return tuple(axis in MODE_AXES.get(key, "XYZ") for axis in "XYZ")


def _update_symmetry(obj):
    """Run on every update for the active object. Works out from the
    object's own stored state (never from what the previous update saw)
    whether its shared X/Y/Z symmetry is the current mode's or another
    mode's, so it gives the right result after an undo too.

    Blender takes its undo snapshot of a mode switch BEFORE this has run, so
    a snapshot can hold the new mode together with the old mode's X/Y/Z.
    `axes_mode` is in the same snapshot and still names the old mode, which
    is how that is spotted and put right when undo lands there.

    In Sculpt Mode this also defaults Fix Poles on the first time."""
    if obj is None or obj.type != 'MESH':
        return
    prefs = _get_prefs()
    memory = obj.symmetry_memory
    key = _storage_key(obj.mode, prefs)
    if not _remembering(prefs):
        # Not managing symmetry: just note whose value X/Y/Z now is, so it
        # is taken as this mode's if the option is turned back on.
        if memory.axes_mode != key:
            memory.axes_mode = key
    else:
        apply = False
        if memory.axes_mode != key:
            # X/Y/Z still hold what another mode was using: remember that
            # for the other mode, then switch to this mode's.
            _store_axes(obj, memory.axes_mode, _editable_in(obj, memory.axes_mode))
            memory.axes_mode = key
            apply = True
        if key:
            state = getattr(memory, key)
            if not state.initialized:
                # First time in this mode: use the preference default.
                state.axes = _default_axes(key)
                state.initialized = True
                apply = True
            if apply:
                _write_axes(obj, tuple(state.axes))
            else:
                # Same mode as before: remember any change just made.
                _store_axes(obj, key, _editable_axes(obj))
    if obj.mode == 'SCULPT' and (prefs is None or prefs.default_fix_poles):
        _ensure_fix_poles_default(obj)


def _apply_current_mode():
    try:
        obj = bpy.context.object
    except AttributeError:
        return
    _update_symmetry(obj)
    _update_armature_pivots()
    _remember_state(obj)


def _apply_current_mode_deferred():
    """One-shot timer callback: run once context is safe, then unregister."""
    _apply_current_mode()
    return None


def _reset_all_memory():
    """Forget every remembered symmetry value so defaults apply again."""
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            obj.armature_pivot_memory.initialized = False
        if obj.type != 'MESH':
            continue
        memory = obj.symmetry_memory
        for key in MODE_KEYS.values():
            getattr(memory, key).initialized = False


# ---------------------------------------------------------------------------
# Armature Edit Mode pivot point
# ---------------------------------------------------------------------------
# The pivot point is ONE scene setting shared by every mode and object. This
# gives Armature Edit Mode its own value: entering it notes the pivot in use
# and applies the armature's remembered pivot (Active Element the first
# time); leaving it remembers the armature's pivot and puts the noted one
# back.
#
# Blender's undo does NOT revert the pivot point, but it does revert custom
# properties. So the record of which scenes currently hold an Edit Mode pivot
# (and what to put back) is kept here in Python, where undo leaves it alone
# just like the pivot itself. It is kept per scene and rechecked from scratch
# on every update, rather than tracked as "entered"/"left" events, so undo,
# scene switches and scene copies can't leave it out of step.
#
# Scene.armature_pivot_restore is only a copy of that record, for the .blend
# file and for scene copies. It is read the first time a scene is looked at
# and never trusted after that.

_live_pivots = {}  # scene session_uid -> [pivot to put back, armature session_uid]
_known_scenes = set()  # session_uids of scenes looked at since load / enable
_preexisting_scenes = None  # session_uids of scenes that came with the project


def _pivot_enabled(prefs):
    return prefs is not None and prefs.armature_edit_pivot


def _is_armature_edit(obj):
    return obj is not None and obj.type == 'ARMATURE' and obj.mode == 'EDIT'


def _context_scene():
    try:
        return bpy.context.scene
    except AttributeError:
        return None


def _forget_pivot_tracking():
    """Start over (project opened, or addon enabled/disabled)."""
    global _preexisting_scenes
    _live_pivots.clear()
    _known_scenes.clear()
    _preexisting_scenes = None


def _object_by_uid(uid):
    for obj in bpy.data.objects:
        if obj.session_uid == uid:
            return obj
    return None


def _set_pivot_copy(scene, live):
    """Match the scene's saved copy of the record to `live` (None = the
    scene isn't holding an Edit Mode pivot)."""
    saved = scene.armature_pivot_restore
    if saved.stored != (live is not None):
        saved.stored = live is not None
    if live is not None and saved.outside != live[0]:
        saved.outside = live[0]


def _write_pivot_copies():
    """Bring the saved copies up to date (undo may have reverted them)."""
    for scene in bpy.data.scenes:
        uid = scene.session_uid
        if uid in _known_scenes:
            _set_pivot_copy(scene, _live_pivots.get(uid))


def _remember_armature_pivot(obj, pivot):
    """Note `pivot` as the one this armature uses in Edit Mode."""
    if obj is None or obj.type != 'ARMATURE':
        return
    state = obj.armature_pivot_memory
    if state.initialized and state.pivot != pivot:
        state.pivot = pivot


def _apply_armature_pivot(obj, settings):
    """Switch the scene to the pivot this armature uses in Edit Mode
    (Active Element if it hasn't been in Edit Mode before)."""
    state = obj.armature_pivot_memory
    if not state.initialized:
        state.pivot = 'ACTIVE_ELEMENT'
        state.initialized = True
    if settings.transform_pivot_point != state.pivot:
        settings.transform_pivot_point = state.pivot


def _scenes_in_view():
    """(scene, active object) for every scene shown in a window."""
    pairs = []
    try:
        windows = bpy.context.window_manager.windows
    except AttributeError:
        windows = ()
    for window in windows:
        try:
            pairs.append((window.scene, window.view_layer.objects.active))
        except AttributeError:
            pass
    if not pairs:
        scene = _context_scene()
        if scene is not None:
            try:
                pairs.append((scene, bpy.context.object))
            except AttributeError:
                pass
    return pairs


def _update_armature_pivots():
    """Run on every update. Every scene on screen is checked, not just the
    one the update came from: leaving Edit Mode in one scene can leave
    another scene (sharing the armature) holding an Edit Mode pivot, and
    nothing updates when that scene is switched back to."""
    global _preexisting_scenes
    if _preexisting_scenes is None:
        _preexisting_scenes = {s.session_uid for s in bpy.data.scenes}
    enabled = _pivot_enabled(_get_prefs())
    done = set()
    for scene, obj in _scenes_in_view():
        uid = scene.session_uid
        if uid not in done:
            done.add(uid)
            _update_scene_pivot(scene, obj, enabled)
    # Scenes not on screen: put the ordinary pivot back once the armature
    # that was being edited there is no longer in Edit Mode.
    waiting = [uid for uid in _live_pivots if uid not in done]
    if waiting:
        scenes = {s.session_uid: s for s in bpy.data.scenes}
        for uid in waiting:
            scene = scenes.get(uid)
            if scene is None:
                del _live_pivots[uid]
            elif not enabled or not _is_armature_edit(_object_by_uid(_live_pivots[uid][1])):
                _update_scene_pivot(scene, None, enabled)


def _pivot_poll():
    """Repeating timer, as a safety net: a few changes cause no update at
    all (a scene copied while in Armature Edit Mode sits untouched until
    something in it changes), so the check is also run twice a second."""
    try:
        if not bpy.app.is_job_running('RENDER'):
            _update_armature_pivots()
    except Exception:
        # Never let an error here stop the timer; the next run tries again.
        pass
    return 0.5


def _update_scene_pivot(scene, obj, enabled):
    """Work out from the current state alone whether this scene's pivot
    should be an armature's Edit Mode pivot or the ordinary one, and switch
    it if it's the wrong one. `obj` is the scene's active object."""
    uid = scene.session_uid
    settings = scene.tool_settings
    first_look = uid not in _known_scenes
    _known_scenes.add(uid)

    if not enabled:
        # Option off: drop the record and leave the pivot as it is.
        _live_pivots.pop(uid, None)
        _set_pivot_copy(scene, None)
        return

    live = _live_pivots.get(uid)
    saved = scene.armature_pivot_restore
    current = settings.transform_pivot_point
    if _is_armature_edit(obj):
        if live is None and first_look and saved.stored:
            # Project saved (or scene copied) while in Armature Edit Mode:
            # the scene pivot already is the Edit Mode one, so keep it.
            live = _live_pivots[uid] = [saved.outside, obj.session_uid]
            if obj.armature_pivot_memory.initialized:
                _remember_armature_pivot(obj, current)
            else:
                _apply_armature_pivot(obj, settings)
        elif live is None:
            # Entering Armature Edit Mode.
            live = _live_pivots[uid] = [current, obj.session_uid]
            _apply_armature_pivot(obj, settings)
        elif live[1] != obj.session_uid:
            # Another armature that is also in Edit Mode became active.
            _remember_armature_pivot(_object_by_uid(live[1]), current)
            live[1] = obj.session_uid
            _apply_armature_pivot(obj, settings)
        else:
            # Still editing the same armature: track any pivot change.
            _remember_armature_pivot(obj, current)
    elif live is not None:
        # No longer in Armature Edit Mode (left it, undid entering it, or
        # came back to this scene after leaving it elsewhere).
        owner = obj if obj is not None and obj.session_uid == live[1] else _object_by_uid(live[1])
        _remember_armature_pivot(owner, current)
        if current != live[0]:
            settings.transform_pivot_point = live[0]
        del _live_pivots[uid]
        live = None
    elif first_look and saved.stored and uid not in _preexisting_scenes:
        # A scene just copied from one that was in Armature Edit Mode: it
        # got that scene's Edit Mode pivot, so give it the ordinary one.
        if current != saved.outside:
            settings.transform_pivot_point = saved.outside
    _set_pivot_copy(scene, live)


# ---------------------------------------------------------------------------
# Running the checks (depsgraph_update_post is reliable; Object.mode msgbus
# notifications are not).
# ---------------------------------------------------------------------------

# What the last update saw. Only used to know which axes were editable in
# the mode an object has just left (see _editable_in); nothing is decided
# from it, because undo can change the object without changing this.
_last_state = (None, None)  # (object name, mode)
_last_editable = (True, True, True)  # axes editable in _last_state's mode


def _remember_state(obj):
    global _last_state, _last_editable
    _last_state = (obj.name, obj.mode) if obj is not None else (None, None)
    _last_editable = _editable_axes(obj) if obj is not None else (True, True, True)


def _check_and_apply_mode_change():
    try:
        obj = bpy.context.object
    except AttributeError:
        return
    _update_symmetry(obj)
    _remember_state(obj)
    _update_armature_pivots()


# ---------------------------------------------------------------------------
# New armature display
# ---------------------------------------------------------------------------
# Only armatures ADDED while an option is on are changed. Everything that
# already exists when a project is opened (or when the addon is enabled) is
# recorded in _seen_objects and never touched, as is anything added while
# both options are off -- so turning one on never restyles existing rigs.

_seen_objects = None  # session_uids to leave alone; None until the baseline is taken
_last_object_count = -1  # a change in this triggers a scan for new objects


def _baseline_armatures():
    """Treat every object that exists right now as already in the project."""
    global _seen_objects, _last_object_count
    _seen_objects = {obj.session_uid for obj in bpy.data.objects}
    _last_object_count = len(bpy.data.objects)


def _baseline_armatures_deferred():
    """One-shot timer callback for when the addon is enabled mid-session."""
    if _seen_objects is None:
        _baseline_armatures()
    return None


def _init_new_armature(obj, prefs):
    uid = obj.session_uid
    if uid in _seen_objects:
        return
    in_front = prefs is not None and prefs.armature_in_front
    wire = prefs is not None and prefs.armature_display_wire
    if (obj.type != 'ARMATURE' or obj.library is not None
            or not (in_front or wire)):
        _seen_objects.add(uid)
        return
    init = obj.armature_display_init
    if init.initialized:
        return
    if in_front:
        obj.show_in_front = True
    if wire:
        obj.display_type = 'WIRE'
    init.initialized = True


def _check_new_armatures():
    global _last_object_count
    if _seen_objects is None:
        return
    prefs = _get_prefs()
    count = len(bpy.data.objects)
    if count != _last_object_count:
        _last_object_count = count
        for obj in bpy.data.objects:
            _init_new_armature(obj, prefs)
        return
    # Object count unchanged: still check the active object, which covers a
    # delete and an add landing in the same update.
    try:
        obj = bpy.context.object
    except AttributeError:
        return
    if obj is not None:
        _init_new_armature(obj, prefs)


@persistent
def _on_undo_redo(_scene, _dummy=None):
    # Undo/redo can bring back an armature from before its display was set
    # (the object count may not change), so force a rescan.
    global _last_object_count
    _last_object_count = -1


@persistent
def _on_depsgraph_update_post(_scene, _depsgraph):
    _check_and_apply_mode_change()
    _check_new_armatures()


@persistent
def _on_load(_dummy):
    global _last_state, _last_editable
    _last_state = (None, None)
    _last_editable = (True, True, True)
    _forget_pivot_tracking()
    _baseline_armatures()
    prefs = _get_prefs()
    if prefs is not None and prefs.apply_defaults_on_load:
        _reset_all_memory()
    bpy.app.timers.register(_apply_current_mode_deferred, first_interval=0.0)


@persistent
def _on_save_pre(*_args):
    # The saved copies are what a reopened project goes by, so make sure
    # they're right before the file is written.
    _write_pivot_copies()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    SmartSymmetryPreferences,
    ModeSymmetryState,
    ObjectSymmetryMemory,
    MeshFixPolesInit,
    ArmaturePivotState,
    ScenePivotRestore,
    ArmatureDisplayInit,
)


def register():
    _forget_pivot_tracking()

    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.symmetry_memory = bpy.props.PointerProperty(type=ObjectSymmetryMemory)
    bpy.types.Mesh.fix_poles_init = bpy.props.PointerProperty(type=MeshFixPolesInit)
    bpy.types.Object.armature_display_init = bpy.props.PointerProperty(type=ArmatureDisplayInit)
    bpy.types.Object.armature_pivot_memory = bpy.props.PointerProperty(type=ArmaturePivotState)
    bpy.types.Scene.armature_pivot_restore = bpy.props.PointerProperty(type=ScenePivotRestore)

    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)
    if _on_depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update_post)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _on_undo_redo not in handlers:
            handlers.append(_on_undo_redo)
    if _on_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(_on_save_pre)

    bpy.app.timers.register(_apply_current_mode_deferred, first_interval=0.0)
    bpy.app.timers.register(_baseline_armatures_deferred, first_interval=0.0)
    if not bpy.app.timers.is_registered(_pivot_poll):
        bpy.app.timers.register(_pivot_poll, first_interval=0.5, persistent=True)


def unregister():
    global _seen_objects
    _seen_objects = None

    # Leave the saved copies correct, so re-enabling the addon while an
    # armature is still in Edit Mode picks up where it left off.
    try:
        _write_pivot_copies()
    except Exception:
        pass
    _forget_pivot_tracking()

    if bpy.app.timers.is_registered(_pivot_poll):
        bpy.app.timers.unregister(_pivot_poll)
    if _on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_on_save_pre)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if _on_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update_post)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _on_undo_redo in handlers:
            handlers.remove(_on_undo_redo)

    del bpy.types.Scene.armature_pivot_restore
    del bpy.types.Object.armature_pivot_memory
    del bpy.types.Object.armature_display_init
    del bpy.types.Mesh.fix_poles_init
    del bpy.types.Object.symmetry_memory
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
