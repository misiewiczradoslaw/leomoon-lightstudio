import bpy
from bpy.props import BoolProperty, StringProperty, PointerProperty, FloatProperty, EnumProperty
import os, sys, subprocess
from . common import *
from itertools import chain
from . operators.modal import close_control_panel
from . import light_list

_ = os.sep

class ListItem(bpy.types.PropertyGroup):
    """ Group of properties representing an item in the list """
    def update_name(self, context):
        print("{} : {}".format(repr(self.name), repr(context)))

    name: StringProperty(
            name="Profile Name",
            default="Untitled")

    empty_name: StringProperty(
            name="Name of Empty that holds the profile",
            description="",
            default="")

class LIST_OT_NewItem(bpy.types.Operator):

    bl_idname = "lls_list.new_profile"
    bl_label = "Add a new profile"
    bl_options = {"INTERNAL"}

    handle: BoolProperty(default=True)

    def execute(self, context):
        props = context.scene.LLStudio
        item = props.profile_list.add()
        lls_collection = get_lls_collection(context)

        # unlink existing profiles
        for profile in (prof for prof in context.scene.objects if prof.name.startswith('LLS_PROFILE.') and isFamily(prof)):
            profile_collection = profile.users_collection[0]
            lls_collection.children.unlink(profile_collection)
        #

        idx = 0
        for id in (i.name.split('Profile ')[1] for i in props.profile_list if i.name.startswith('Profile ')):
            try:
                id = int(id)
            except ValueError:
                continue

            if id > idx: idx = id

        item.name = 'Profile '+str(idx+1)

        ''' Add Hierarchy stuff '''
        # before
        A = set(bpy.data.objects[:])

        script_file = os.path.realpath(__file__)
        dir = os.path.dirname(script_file)
        bpy.ops.wm.append(filepath=_+'LLS3.blend'+_+'Object'+_,
            directory=os.path.join(dir,"LLS3.blend"+_+"Object"+_),
            filename="LLS_PROFILE.000",
            active_collection=True)

        # after operation
        B = set(bpy.data.objects[:])

        # whats the difference
        profile = (A ^ B).pop()

        profile.parent = [ob for ob in context.scene.objects if ob.name.startswith('LEOMOON_LIGHT_STUDIO')][0]
        profile.use_fake_user = True
        profile_collection = bpy.data.collections.new(profile.name)
        profile_collection.use_fake_user = True
        lls_collection = [c for c in context.scene.collection.children if c.name.startswith('LLS')][0]
        lls_collection.children.link(profile_collection)
        replace_link(profile, profile.name)

        item.empty_name = profile.name

        handle = None
        if self.handle:
            bpy.ops.object.empty_add()
            handle = context.active_object
            handle.name = "LLS_HANDLE"
            handle.empty_display_type = 'SPHERE'
            handle.parent = profile
            handle.protected = True
            handle.use_fake_user = True
            replace_link(handle, profile.name)

        props.last_empty = profile.name
        props.list_index = len(props.profile_list)-1

        light_list.update_light_list_set(context)

        return{'FINISHED'}

class LIST_OT_DeleteItem(bpy.types.Operator):

    bl_idname = "lls_list.delete_profile"
    bl_label = "Delete the selected profile"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(self, context):
        """ Enable if there's something in the list """
        return len(context.scene.LLStudio.profile_list)

    def execute(self, context):
        props = context.scene.LLStudio
        index = props.list_index

        props.profile_list.remove(index)

        ''' Delete/Switch Hierarchy stuff '''
        #delete objects from current profile
        obsToRemove = family(context.scene.objects[props.last_empty])
        collectionsToRemove = set()
        for ob in obsToRemove:
            collectionsToRemove.update(ob.users_collection)
            ob.use_fake_user = False
        bpy.ops.object.delete({"selected_objects": obsToRemove}, use_global=True)
        for c in collectionsToRemove:
            if c.name.startswith('LLS_'):
                bpy.data.collections.remove(c)

        # update index
        if index > 0:
            index = index - 1
        props.list_index = index

        light_list.update_light_list_set(context)

        return{'FINISHED'}

class LIST_OT_CopyItem(bpy.types.Operator):

    bl_idname = "lls_list.copy_profile"
    bl_label = "Copy profile"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(self, context):
        """ Enable if there's something in the list. """
        return len(context.scene.LLStudio.profile_list)

    def execute(self, context):
        props = context.scene.LLStudio
        list = props.profile_list

        lls_collection, profile_collection = llscol_profilecol(context)

        profile_copy = duplicate_collection(profile_collection, None)
        profile = [ob for ob in profile_copy.objects if ob.name.startswith('LLS_PROFILE')][0]
        handle = [ob for ob in profile.children if ob.name.startswith('LLS_HANDLE')][0]

        for l in [lm for lc in profile_copy.children if lc.name.startswith('LLS_Light') for lm in lc.objects if lm.name.startswith('LLS_LIGHT_MESH')]:
            l.constraints['Copy Location'].target = handle

        new_list_item = props.profile_list.add()
        new_list_item.empty_name = profile_copy.name_full
        new_list_item.name = props.profile_list[props.list_index].name + ' Copy'

        # place copied profile next to source profile
        lastItemId = len(props.profile_list)-1
        while lastItemId > props.list_index+1:
            list.move(lastItemId-1, lastItemId)
            lastItemId -= 1

        return{'FINISHED'}



class LIST_OT_MoveItem(bpy.types.Operator):

    bl_idname = "lls_list.move_profile"
    bl_label = "Move profile"
    bl_options = {"INTERNAL"}

    direction: bpy.props.EnumProperty(
                items=(
                    ('UP', 'Up', ""),
                    ('DOWN', 'Down', ""),))

    @classmethod
    def poll(self, context):
        """ Enable if there's something in the list. """
        return len(context.scene.LLStudio.profile_list)


    def move_index(self, context):
        """ Move index of an item render queue while clamping it. """
        props = context.scene.LLStudio
        index = props.list_index
        list_length = len(props.profile_list) - 1 # (index starts at 0)
        new_index = 0

        if self.direction == 'UP':
            new_index = index - 1
        elif self.direction == 'DOWN':
            new_index = index + 1

        new_index = max(0, min(new_index, list_length))
        props.list_index = new_index


    def execute(self, context):
        props = context.scene.LLStudio
        list = props.profile_list
        index = props.list_index

        if self.direction == 'DOWN':
            neighbor = index + 1
            list.move(index,neighbor)
        elif self.direction == 'UP':
            neighbor = index - 1
            list.move(neighbor, index)
        else:
            return{'CANCELLED'}
        self.move_index(context)

        return{'FINISHED'}

def update_list_index(self, context):
    props = context.scene.LLStudio

    if len(props.profile_list) == 0: return

    selected_profile = props.profile_list[self.list_index]

    if selected_profile.empty_name == props.last_empty: return

    print('Index update {}'.format(self.list_index))

    #unlink current profile
    lls_collection = get_lls_collection(context)
    profile_collection = [c for c in lls_collection.children if c.name.startswith('LLS_PROFILE')]
    profile_collection = profile_collection[0] if profile_collection else None
    if profile_collection:
        lls_collection.children.unlink(profile_collection)

    #link selected profile
    lls_collection.children.link(bpy.data.collections[selected_profile.empty_name])

    props.last_empty = selected_profile.empty_name

    from . operators.modal import update_light_sets, panel_global
    if panel_global:
        update_light_sets(panel_global, bpy.context, always=True)

    light_list.update_light_list_set(context)

# import/export
import json, time
script_file = os.path.realpath(__file__)
dir = os.path.dirname(script_file)

VERSION = 2.01
def parse_profile(context, props, profiles, version=VERSION, internal_copy=False):
    plist = props.profile_list
    for profile in profiles:
        print(profile)
        bpy.ops.lls_list.new_profile()
        props.list_index = len(plist)-1
        plist[-1].name = profile["name"]
        if not internal_copy:
            date = time.localtime()
            plist[-1].name += ' {}-{:02}-{:02} {:02}:{:02}'.format(str(date.tm_year)[-2:], date.tm_mon, date.tm_mday, date.tm_hour, date.tm_min)

        profile_empty = context.scene.objects[plist[-1].empty_name]

        if version > 1:
            handle = getLightHandle(profile_empty)
            handle.location.x = profile['handle_position'][0]
            handle.location.y = profile['handle_position'][1]
            handle.location.z = profile['handle_position'][2]

        for light in profile["lights"]:
            # before
            A = set(profile_empty.children)

            bpy.ops.scene.add_leomoon_studio_light()

            # after operation
            B = set(profile_empty.children)

            # whats the difference
            lgrp = (A ^ B).pop()

            actuator = [c for c in family(lgrp) if "LLS_ROTATION" in c.name][0]
            lmesh = [c for c in family(lgrp) if "LLS_LIGHT_MESH" in c.name][0]
            lmesh.location.x = light['radius']

            actuator.rotation_euler.x = light['position'][0]
            actuator.rotation_euler.y = light['position'][1]
            actuator.rotation_euler.z = 0

            lmesh.scale.x = light['scale'][0]
            lmesh.scale.y = light['scale'][1]
            lmesh.scale.z = light['scale'][2]

            lmesh.rotation_euler.x = light['rotation']

            if 'light_name' in light:
                lmesh.LLStudio.light_name = light['light_name']
            if 'order_index' in light:
                lmesh.LLStudio.order_index = light['order_index']

            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[2].default_value = light['Texture Switch']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value[0] = light['Color Overlay'][0]
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value[1] = light['Color Overlay'][1]
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value[2] = light['Color Overlay'][2]
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value[3] = light['Color Overlay'][3]
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[4].default_value = light['Color Saturation']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[5].default_value = light['Intensity']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[6].default_value = light['Mask - Gradient Switch']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[7].default_value = light['Mask - Gradient Type']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[8].default_value = light['Mask - Gradient Amount']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[9].default_value = light['Mask - Ring Switch']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[10].default_value = light['Mask - Ring Inner Radius']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[11].default_value = light['Mask - Ring Outer Radius']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[12].default_value = light['Mask - Top to Bottom']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[13].default_value = light['Mask - Bottom to Top']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[14].default_value = light['Mask - Left to Right']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[15].default_value = light['Mask - Right to Left']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[16].default_value = light['Mask - Diagonal Top Left']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[17].default_value = light['Mask - Diagonal Top Right']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[18].default_value = light['Mask - Diagonal Bottom Right']
            lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[19].default_value = light['Mask - Diagonal Bottom Left']

            # lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value = light['Opacity']
            # lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[4].default_value = light['Falloff']
            # lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[5].default_value = light['Color Saturation']
            # lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[6].default_value = light['Half']

            if os.path.isabs(light['tex']):
                lmesh.material_slots[0].material.node_tree.nodes["Light Texture"].image.filepath = light['tex']
            else:
                lmesh.material_slots[0].material.node_tree.nodes["Light Texture"].image.filepath = os.path.join(dir, "textures_real_lights", light['tex'])

class ImportProfiles(bpy.types.Operator):

    bl_idname = "lls_list.import_profiles"
    bl_label = "Import profiles"
    bl_description = "Import profiles from file"
    #bl_options = {"INTERNAL"}

    filepath: bpy.props.StringProperty(default="*.lls", subtype="FILE_PATH")

    @classmethod
    def poll(self, context):
        return True

    def execute(self, context):
        props = context.scene.LLStudio

        with open(self.filepath, 'r') as f:
            file = f.read()
        f.closed

        file = json.loads(file)
        parse_profile(context, props, file["profiles"], float(file["version"]))
        light_list.update_light_list_set(context)

        return{'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

def compose_profile(list_index):
    props = bpy.context.scene.LLStudio
    profile_dict = {}
    profile_dict['name'] = props.profile_list[list_index].name
    profile_dict['lights']= []
    profile = bpy.data.objects[props.profile_list[list_index].empty_name]
    profile_collection = get_collection(profile)
    handle = getLightHandle(profile)
    profile_dict['handle_position'] = [handle.location.x, handle.location.y, handle.location.z]
    for light_collection in profile_collection.children:
        lmesh = [ob for ob in light_collection.objects if ob.name.startswith('LLS_LIGHT_MESH')][0]
        actuator = [ob for ob in light_collection.objects if ob.name.startswith('LLS_ROTATION')][0]
        light = {}
        light['light_name'] = lmesh.LLStudio.light_name
        light['order_index'] = lmesh.LLStudio.order_index
        light['radius'] = lmesh.location.x
        light['position'] = [actuator.rotation_euler.x, actuator.rotation_euler.y]
        light['scale'] = [lmesh.scale.x, lmesh.scale.y, lmesh.scale.z]
        light['rotation'] = lmesh.rotation_euler.x
        # view_layer = find_view_layer(light_collection, bpy.context.view_layer.layer_collection)
        # light['mute'] = view_layer.exclude
        texpath = lmesh.material_slots[0].material.node_tree.nodes["Light Texture"].image.filepath
        light['tex'] = texpath.split(bpy.path.native_pathsep("\\textures_real_lights\\"))[-1]

        light['Texture Switch'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[2].default_value
        light['Color Overlay'] = [lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value[0],
                                  lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value[1],
                                  lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value[2],
                                  lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value[3]]
        light['Color Saturation'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[4].default_value
        light['Intensity'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[5].default_value
        light['Mask - Gradient Switch'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[6].default_value
        light['Mask - Gradient Type'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[7].default_value
        light['Mask - Gradient Amount'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[8].default_value
        light['Mask - Ring Switch'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[9].default_value
        light['Mask - Ring Inner Radius'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[10].default_value
        light['Mask - Ring Outer Radius'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[11].default_value
        light['Mask - Top to Bottom'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[12].default_value
        light['Mask - Bottom to Top'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[13].default_value
        light['Mask - Left to Right'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[14].default_value
        light['Mask - Right to Left'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[15].default_value
        light['Mask - Diagonal Top Left'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[16].default_value
        light['Mask - Diagonal Top Right'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[17].default_value
        light['Mask - Diagonal Bottom Right'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[18].default_value
        light['Mask - Diagonal Bottom Left'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[19].default_value

        # light['Intensity'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[2].default_value
        # light['Opacity'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[3].default_value
        # light['Falloff'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[4].default_value
        # light['Color Saturation'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[5].default_value
        # light['Half'] = lmesh.material_slots[0].material.node_tree.nodes["Group"].inputs[6].default_value

        profile_dict['lights'].append(light)
        profile_dict['lights'].sort(key=lambda x: x["order_index"])

    return profile_dict

class ExportProfiles(bpy.types.Operator):

    bl_idname = "lls_list.export_profiles"
    bl_label = "Export profiles to file"
    bl_description = "Export profile(s) to file"
    #bl_options = {"INTERNAL"}

    filepath: bpy.props.StringProperty(default="profile.lls", subtype="FILE_PATH")
    all: bpy.props.BoolProperty(default=False, name="Export All Profiles")

    @classmethod
    def poll(self, context):
        """ Enable if there's something in the list """
        return len(context.scene.LLStudio.profile_list)

    def execute(self, context):
        props = context.scene.LLStudio
        index = props.list_index

        export_file = {}
        date = time.localtime()
        export_file['date'] = '{}-{:02}-{:02} {:02}:{:02}'.format(date.tm_year, date.tm_mon, date.tm_mday, date.tm_hour, date.tm_min)
        export_file['version'] = VERSION
        profiles_to_export = export_file['profiles'] = []

        if self.all:
            for p in range(len(props.profile_list)):
                try:
                    profiles_to_export.append(compose_profile(p))
                except Exception:
                    self.report({'WARNING'}, 'Malformed profile %s. Omitting.' % props.profile_list[p].name)
        else:
            try:
                profiles_to_export.append(compose_profile(index))
            except Exception:
                self.report({'WARNING'}, 'Malformed profile %s. Omitting.' % props.profile_list[index].name)

        with open(self.filepath, 'w') as f:
            f.write(json.dumps(export_file, indent=4))
        f.closed

        return{'FINISHED'}

    def invoke(self, context, event):
        self.filepath = "profile.lls"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class FindMissingTextures(bpy.types.Operator):

    bl_idname = "lls.find_missing_textures"
    bl_label = "Find Missing Textures"
    bl_description = "Find missing light textures"
    #bl_options = {"INTERNAL"}

    @classmethod
    def poll(self, context):
        """ Enable if there's something in the list """
        return len(context.scene.LLStudio.profile_list)

    def execute(self, context):
        bpy.ops.file.find_missing_files(directory=os.path.join(dir, "textures_real_lights"))
        bpy.context.scene.frame_current = bpy.context.scene.frame_current
        return{'FINISHED'}

class OpenTexturesFolder(bpy.types.Operator):

    bl_idname = "lls.open_textures_folder"
    bl_label = "Open Textures Folder"
    bl_description = "Open textures folder"
    #bl_options = {"INTERNAL"}

    #@classmethod
    #def poll(self, context):
    #    """ Enable if there's something in the list """
    #    return len(context.scene.LLStudio.profile_list)

    def execute(self, context):
        path = os.path.join(dir, "textures_real_lights")
        if sys.platform == 'darwin':
            subprocess.Popen(["open", path])
        elif sys.platform == 'linux2':
            subprocess.Popen(["xdg-open", path])
        elif sys.platform == 'win32':
            subprocess.Popen(["explorer", path])
        return{'FINISHED'}

class CopyProfileToScene(bpy.types.Operator):
    """ Copy Light Profile to Scene """

    bl_idname = "lls_list.copy_profile_to_scene"
    bl_label = "Copy Profile to Scene"
    bl_property = "sceneprop"

    def get_scenes(self, context):
        return ((s.name, s.name, "Scene name") for i,s in enumerate(bpy.data.scenes))#global_vars["scenes"]

    sceneprop: EnumProperty(items = get_scenes)

    @classmethod
    def poll(self, context):
        """ Enable if there's something in the list """
        return len(context.scene.LLStudio.profile_list)

    def execute(self, context):
        props = context.scene.LLStudio
        index = props.list_index

        profiles = [compose_profile(index),]

        context.window.scene = bpy.data.scenes[self.sceneprop]
        context.scene.render.engine = 'CYCLES'
        if not context.scene.LLStudio.initialized:
            bpy.ops.scene.create_leomoon_light_studio()

        parse_profile(context, context.scene.LLStudio, profiles, internal_copy=True)

        close_control_panel()

        return{'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.invoke_search_popup(self)
        return {'FINISHED'}


class CopyProfileMenu(bpy.types.Operator):

    bl_idname = "lls_list.copy_profile_menu"
    bl_label = "Copy selected profile"

    @classmethod
    def poll(self, context):
        """ Enable if there's something in the list """
        return len(context.scene.LLStudio.profile_list)

    def execute(self, context):
        wm = context.window_manager
        def draw(self, context):
            layout = self.layout
            layout.operator_context='INVOKE_AREA'
            col = layout.column(align=True)
            col.operator('lls_list.copy_profile')
            col.operator('lls_list.copy_profile_to_scene')

        wm.popup_menu(draw, title="Copy Profile")
        return {'FINISHED'}