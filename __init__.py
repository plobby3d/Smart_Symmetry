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
# The memory is stored on each object, so it is saved in the .blend file and
# comes back when the project is reopened (unless "Apply Defaults When
# Opening a Project" is on, which clears it on load).
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
    'texture_paint': (True, False, False),
}

# Weight Paint only supports X symmetry, so only X is offered for it.
MODE_AXES = {
    'weight_paint': "X",
}

# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

class SmartSymmetryPreferences(bpy.types.AddonPreferences):
    # For an extension this is the package name Blender installs it under
    # (bl_ext.<repository>.smart_symmetry), which __package__ resolves to.
    bl_idname = __package__

    remember_symmetry: bpy.props.BoolProperty(
        name="Remember Symmetry per Mode",
        description=(
            "Remember each object's XYZ symmetry separately for Edit, Sculpt, "
            "Vertex Paint, Texture Paint and Weight Paint, and reapply it "
            "when that mode is entered. When off, the addon doesn't change "
            "symmetry (Fix Poles is unaffected)"
        ),
        default=True,
    )
    apply_defaults_on_load: bpy.props.BoolProperty(
        name="Apply Defaults When Opening a Project",
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
        layout.prop(self, "apply_defaults_on_load")

        box = layout.box()
        box.label(text="Default Symmetry")
        col = box.column(align=True)
        for key, label in MODE_LABELS.items():
            split = col.split(factor=0.3, align=True)
            split.label(text=label)
            row = split.row(align=True)
            for index, axis in enumerate(MODE_AXES.get(key, "XYZ")):
                row.prop(self, "default_%s_symmetry" % key, index=index, text=axis, toggle=True)

        layout.prop(self, "default_fix_poles")


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


class MeshFixPolesInit(bpy.types.PropertyGroup):
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


def _mode_state(obj, mode):
    key = MODE_KEYS.get(mode)
    return getattr(obj.symmetry_memory, key) if key is not None else None


def _remembering(prefs):
    return prefs is None or prefs.remember_symmetry


def _apply_mode_symmetry(obj):
    """Entering a mode: reapply the symmetry this object last used there, or
    the preference default if it has never been in this mode. In Sculpt Mode
    this also defaults Fix Poles on the first time."""
    if obj is None or obj.type != 'MESH':
        return
    prefs = _get_prefs()
    state = _mode_state(obj, obj.mode)
    if state is not None and _remembering(prefs):
        if not state.initialized:
            state.axes = _default_axes(MODE_KEYS[obj.mode])
            state.initialized = True
        _write_axes(obj, tuple(state.axes))
    if obj.mode == 'SCULPT' and (prefs is None or prefs.default_fix_poles):
        _ensure_fix_poles_default(obj)


def _store_axes(obj, mode, editable):
    """Save the object's current symmetry as the remembered value for `mode`.
    Axes that weren't editable in that mode keep their remembered value, and
    nothing is saved for a mode this object hasn't been initialized for."""
    if obj is None or obj.type != 'MESH':
        return
    state = _mode_state(obj, mode)
    if state is None or not state.initialized:
        return
    current = _read_axes(obj)
    merged = tuple(current[i] if editable[i] else state.axes[i] for i in range(3))
    if tuple(state.axes) != merged:
        state.axes = merged


def _sync_memory(obj):
    """While still in the same mode on the same object, keep that mode's
    memory matched to any manual toggle the user just made."""
    global _last_editable
    if obj is None:
        return
    _last_editable = _editable_axes(obj)
    if _remembering(_get_prefs()):
        _store_axes(obj, obj.mode, _last_editable)


def _apply_current_mode():
    try:
        obj = bpy.context.object
    except AttributeError:
        return
    _apply_mode_symmetry(obj)
    _remember_state(obj)


def _apply_current_mode_deferred():
    """One-shot timer callback: run once context is safe, then unregister."""
    _apply_current_mode()
    return None


def _reset_all_memory():
    """Forget every remembered symmetry value so defaults apply again."""
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        memory = obj.symmetry_memory
        for key in MODE_KEYS.values():
            getattr(memory, key).initialized = False


# ---------------------------------------------------------------------------
# Mode-change detection (depsgraph_update_post is reliable; Object.mode
# msgbus notifications are not).
# ---------------------------------------------------------------------------

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
    current = (obj.name, obj.mode) if obj is not None else (None, None)
    if current != _last_state:
        prev_name, prev_mode = _last_state
        if _remembering(_get_prefs()):
            # The shared symmetry value still holds what the previous mode
            # used (nothing has been applied yet), so save it before the new
            # mode's value overwrites it.
            prev_obj = bpy.data.objects.get(prev_name) if prev_name else None
            _store_axes(prev_obj, prev_mode, _last_editable)
        _apply_mode_symmetry(obj)
        _remember_state(obj)
        return
    # Same object, same mode as last tick: just keep memory in sync.
    _sync_memory(obj)


@persistent
def _on_depsgraph_update_post(_scene, _depsgraph):
    _check_and_apply_mode_change()


@persistent
def _on_load(_dummy):
    global _last_state, _last_editable
    _last_state = (None, None)
    _last_editable = (True, True, True)
    prefs = _get_prefs()
    if prefs is not None and prefs.apply_defaults_on_load:
        _reset_all_memory()
    bpy.app.timers.register(_apply_current_mode_deferred, first_interval=0.0)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    SmartSymmetryPreferences,
    ModeSymmetryState,
    ObjectSymmetryMemory,
    MeshFixPolesInit,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.symmetry_memory = bpy.props.PointerProperty(type=ObjectSymmetryMemory)
    bpy.types.Mesh.fix_poles_init = bpy.props.PointerProperty(type=MeshFixPolesInit)

    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)
    if _on_depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update_post)

    bpy.app.timers.register(_apply_current_mode_deferred, first_interval=0.0)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if _on_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update_post)

    del bpy.types.Mesh.fix_poles_init
    del bpy.types.Object.symmetry_memory
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
