import os

import glob

import re

import itertools

import functools
import sys

from config import *

#######
#
# UTIL functions
#
#######

def get_scripts_from_category_p(game_path, modid, cat):
    paths = get_scripts(game_path, modid, "%s/*.txt" % cat)
    result = []
    for p in paths:
        with open(p, 'rb') as f:
            result.append([p, f.read()])
    return result

def get_segments_from_category_p(game_path, modid, cat, simple=False):
    """
    get all txt files under `game_path/modid/cat/*.txt` and parse them. (glob wildcard accepted)

    Set `simple=True` to switch to simple mode.\n
    complex mode is default.

    simple mode ... each segments in top-level must be in format `segment_name = { ... }`, not `segment_name = segment_value`.\n
        otherwise the latter one will be regarded as a comment!\n
        useful in top-level file parsing.\n
        keeps comments and other rubbish data except at end of a file.\n
        thus, each segment ends with `}`\n
        but the beginning of each segment may be whitespace, tab, newline or `#`.\n
    
    complex mode ... parse each item as a nested list structure. support statements like `a = b` in top-level\n
        dispose all comments\n
        each item will be parsed as a list which consists of a property name bytes, `b'='` or other equal-like statement such as `b'>='`, a property value bytes, or another list (which means another level of data within `{ ... }`)
    """
    if simple:
        f = get_segments_simple
    else:
        f = get_segments_complex
    return list(itertools.chain.from_iterable(map(lambda x: [x[0], f(x[1])], get_scripts_from_category_p(game_path, modid, cat))))


def get_scripts_from_category(game_path, modid, cat):
    paths = get_scripts(game_path, modid, "%s/*.txt" % cat)
    result = []
    for p in paths:
        with open(p, 'rb') as f:
            result.append(f.read())
    return result

def get_segments_from_category(game_path, modid, cat, simple=False):
    """
    get all txt files under `game_path/modid/cat/*.txt` and parse them. (glob wildcard accepted)

    Set `simple=True` to switch to simple mode.\n
    complex mode is default.

    simple mode ... each segments in top-level must be in format `segment_name = { ... }`, not `segment_name = segment_value`.\n
        otherwise the latter one will be regarded as a comment!\n
        useful in top-level file parsing.\n
        keeps comments and other rubbish data except at end of a file.\n
        thus, each segment ends with `}`\n
        but the beginning of each segment may be whitespace, tab, newline or `#`.\n
    
    complex mode ... parse each item as a nested list structure. support statements like `a = b` in top-level\n
        dispose all comments\n
        each item will be parsed as a list which consists of a property name bytes, `b'='` or other equal-like statement such as `b'>='`, a property value bytes, or another list (which means another level of data within `{ ... }`)
    """
    if simple:
        f = get_segments_simple
    else:
        f = get_segments_complex
    return list(itertools.chain.from_iterable(map(f, get_scripts_from_category(game_path, modid, cat))))

def get_scripts(game_path, modid, query):
    return list(glob.glob(os.path.join(game_path, modid, query)))

from enum import Enum

class InlineOption(Enum):
    Trim = 1
    Substitute = 2
    Functional = 3
    DoNothing = 4

# TODO: implement inline script
def process_inline(spl, inline_option):
    inlines = list(filter(lambda x: x[0] == b'inline_script', spl))
    if len(inlines) > 0:
        print("WARNING!!!! inline script!!!!!!!")
        match inline_option:
            case InlineOption.Trim:
                return list(filter(lambda x: x[0] != b'inline_script', spl))
            case InlineOption.Substitute:
                print("WARNING@@@@!@!@!! not implemented but contnuing anyway (as Trim option)!!!!!")
                return list(filter(lambda x: x[0] != b'inline_script', spl))
            case InlineOption.Functional:
                raise NotImplementedError("not implemented")
            case InlineOption.DoNothing:
                return spl
        
    else:
        return spl

def get_segments_complex(scr):
    comment = False
    current_ptr = []
    parent_ptrs = []
    result = current_ptr
    separation = False
    eq_no_separate = False
    
    for char in scr:
        char = char.to_bytes(1, 'big')
        match char:
            case b'{':
                if not comment:
                    parent_ptrs.append(current_ptr)
                    x = []
                    current_ptr.append(x)
                    current_ptr = x
            case b'}':
                if not comment:
                    current_ptr = parent_ptrs.pop()
            case b'#':
                comment = True
            case b'\n' | b'\r' | b' ' | b'\t' | b'\f' | b'\v':
                if char == b'\n' or char == b'\r':
                    comment = False
                if comment == False:
                    separation = True
            case x:
                if not comment:
                    if x == b'=' and not eq_no_separate:
                        separation = True
                    if eq_no_separate:
                        eq_no_separate = False
                    if x == b'>' or x == b'<' or x == b'!':
                        eq_no_separate = True
                    if len(current_ptr) == 0:
                        current_ptr.append(x)
                    elif isinstance(current_ptr[-1], list):
                        current_ptr.append(x)
                    elif separation:
                        current_ptr.append(x)
                    elif isinstance(current_ptr[-1], bytes):
                        current_ptr[-1] += x
                    else:
                        raise NotImplementedError('not implemented case')
                    if x != b'=':
                        separation = False

    return result

def is_eq_like(c):
    return c == b'=' or c == b'>=' or c == b'<=' or c == b'<' or c == b'>' or c == b'!='

def split3(target, inline_option):
    """
    Splits target into a list of length-3 lists.\n
    Asserts that `len(target) % 3 == 0` and the middle element of each list is '=' or ''!=' or '>=' and so on.\n
    Useful for additional parsing after finishing complex mode parsing
    """
    assert len(target) % 3 == 0
    out = [target[i:i+3] for i in range(0, len(target), 3)]
    assert all([is_eq_like(x[1]) for x in out])
    return process_inline(out, inline_option)

def get_segments_simple(scr):
    result = []
    first_bracket_arrived = False
    comment = False
    nest = 0
    segment = b""
    for char in scr:
        char = char.to_bytes(1, 'big')
        match char:
            case b'{':
                if not comment:
                    nest += 1
                    first_bracket_arrived = True
            case b'}':
                if not comment:
                    nest -= 1
            case b'#':
                comment = True
            case b'\n':
                comment = False
        segment += char
        if first_bracket_arrived and nest == 0:
            result.append(segment)
            segment = b""
            first_bracket_arrived = False
    return result

def patchpath(p):
    return os.path.join(os.path.dirname(__file__), "../", p)

def get_field(target, name):
    """
    Get a value corresponding `name` from target
    REMEMBER that `target` must be in the format AFTER passing to split3.
    """
    try:
        return next(filter(lambda x: x[0] == name, target))[2]
    except StopIteration:
        return None

def get_field_after(target: list, name, n=2):
    """
    Get a value after n tokens from the first occurence of name
    useful for segments that cannot parsed by split3
    """
    try:
        return target[target.index(name) + n]
    except ValueError:
        return None

def add_to_field(target, path, contents, inline_option):
    """
    Add `contents` to the target, according to the path specified by `path`.
    if the specified path does not exist, it will create one.
    REMEMBER that `target` must be in the format BRFORE passing to split3, except in the case `path = []`, which means direct addition to the target.
    Also, all the subcomponents that is addressed by `path` (except the last item of `path`), must pass the sanity check from split3.
    """
    if len(path) == 0:
        for c in contents:
            target.append(c)
    else:
        spl = split3(target, inline_option)
        field = get_field(spl, path[0])
        if field == None:
            obj = [path[0], b'=', []]
            target += obj
            spl.append(obj)
            field = obj[2]
        add_to_field(field, path[1:], contents, inline_option)

def export_fields(target, tabs=0):
    """
    export fields as a byte string\n
    REMEMBER that `target` must be in the format BRFORE passing to `split3` \n
    (which means `target` must get concatenated after passing to `split3`)
    """
    def routine(tup, token):
        data, after_eq, line = tup
        t = (b' ' * tabs)
        if is_eq_like(token):
            after_eq = 1
        if isinstance(token, list):
            data += b'{\n' + export_fields(token, tabs=tabs+4) + t +  b'}'
        else:
            data += (t if line else b'') + token + (b' ' if after_eq != 2 else b'')
        
        line = False
        if after_eq == 1:
            after_eq += 1
        elif after_eq == 2:
            data += b'\n'
            after_eq = 0
            line = True
        
        return (data, after_eq, line)
    return functools.reduce(routine, target, (b'', 0, True))[0]

def nestedSearch(nested, v):
    """
    check for any v(x) where x is an element of given nested list recursively
    """
    for element in nested:
        if isinstance(element, list):
            if nestedSearch(element, v):
                return True
        elif v(element):
            return True
    return False

def nestedSearchList(nested, v):
    """
    check for any v(x) where x is a sub-list of given nested list
    """
    if v(nested):
        return True
    for element in nested:
        if isinstance(element, list):
            if nestedSearchList(element, v):
                return True
    return False


def nestedApply(nested, v):
    """
    execute v(x) recursively in given nested list, where x is a sub-list of given nested list
    """
    v(nested)
    for element in nested:
        if isinstance(element, list):
            nestedApply(element, v)

#######
#
# Indivisual scripts for mods
#
#######

# buildings

def all_buildings():
    var_def_table = {}
    out = b""

    for modid in ['v'] + os.listdir(stellaris_path):
        if modid == 'v' or os.path.isdir(os.path.join(stellaris_path, modid)):
            print('processing modid ', modid)

            if modid in mod_excludes:
                print(" .... skipping this mod")
                continue

            if modid == 'v':
                all_segments = split3(get_segments_from_category(stellaris_game_path, '.', "common/buildings", simple=False), InlineOption.Substitute)
            else:
                all_segments = split3(get_segments_from_category(stellaris_path, modid, "common/buildings", simple=False), InlineOption.Substitute)
            
            building_defs = list(filter(lambda x: not x[0].startswith(b"@"), all_segments))
            var_defs = list(filter(lambda x: x[0].startswith(b"@"), all_segments))
            
            def search(x):
                if b"num_pops" in x:
                    i = x.index(b"num_pops")
                    return is_eq_like(x[i+1]) and re.match(rb"\d+", x[i+2])
                elif b"num_sapient_pops" in x:
                    i = x.index(b"num_sapient_pops")
                    return is_eq_like(x[i+1]) and re.match(rb"\d+", x[i+2])
                else:
                    return False
            
            # TODO: sapient
            def apply(x):
                indices = [i for i, v in enumerate(x) if v == b"num_pops" or v == b"num_sapient_pops"]
                for i in indices:
                    # MYCOMPAT_st_totalpop = { MORE = %s }
                    x[i] = b"MYCOMPAT_st_totalpop"
                    n = x[i + 2]
                    if n.startswith(b"@"):
                        n = [z[2] for z in var_defs if z[0] == n][0]
                    match x[i + 1]:
                        case b'>=':
                            r = [ b"MORE", b"=", str(int(n) - 1).encode()]
                        case b'<=':
                            r = [ b"LESS", b"=", str(int(n) + 1).encode()]
                        case b'>':
                            r = [ b"MORE", b"=", str(int(n)).encode()]
                        case b'<':
                            r = [ b"LESS", b"=", str(int(n)).encode()]
                        case _:
                            raise NotImplementedError("ERROR: unsupported num_pops / num_sapient_pops")
                    x[i + 1] = b"="
                    x[i + 2] = r
            
            building_overrides = []
            
            for building_def in building_defs:
                if nestedSearchList(building_def, search):
                    nestedApply(building_def, apply)
                    building_overrides.append(building_def)
            
            if len(building_overrides):
                for v in var_defs:
                    if v[0] in var_def_table and var_def_table[v[0]] != v[2]:
                        print("WARNING!!! variable already registered!!!!!! %s : prev value %s <-> conflicting value %s" % (v[0],  var_def_table[v[0]], v[2]))
                    var_def_table[v[0]] = v[2]
                
                for ov in building_overrides:
                    out += export_fields(ov)

    for x, y in var_def_table.items():
        out = export_fields([x, b'=', y]) + out
                
    with open(patchpath("common/buildings/%sbuildings_patch.txt" % file_prefix), "wb") as f:
        f.write(out)

# jobs

def calculate_mod_index_from_mod_order(m):
    if m == 'v':
        return (-99999, m)
    else:
        return (mod_order.index(m), m)

def all_jobs():
    """
    ALL JOBS PATCH!
    """

    """
    ========================
     Generate Job & Deposit
    ========================
    """
    job_output = b''
    deposit_output = b''
    sv_output = b''

    job_to_modid = {}
    job_def_table = {}
    var_def_table = {}

    for modid in ['v'] + os.listdir(stellaris_path):
        if modid == 'v' or os.path.isdir(os.path.join(stellaris_path, modid)):
            print('processing modid ', modid)

            if modid in mod_excludes:
                print(" .... skipping this mod")
                continue

            if modid == 'v':
                all_segments = split3(get_segments_from_category(stellaris_game_path, '.', "common/pop_jobs", simple=False), InlineOption.Substitute)
            else:
                all_segments = split3(get_segments_from_category(stellaris_path, modid, "common/pop_jobs", simple=False), InlineOption.Substitute)

            job_defs = list(filter(lambda x: not x[0].startswith(b"@"), all_segments))

            var_defs = list(filter(lambda x: x[0].startswith(b"@"), all_segments))
            for v in var_defs:
                if v[0] in var_def_table and var_def_table[v[0]] != v[2]:
                    print("WARNING!!! variable already registered!!!!!! %s : prev value %s <-> conflicting value %s" % (v[0],  var_def_table[v[0]], v[2]))
                var_def_table[v[0]] = v[2]

            jobnames = list([y[0] for y in job_defs])
            for n in jobnames:
                if not n in job_to_modid:
                    job_to_modid[n] = []
                job_to_modid[n].append(modid)
            
            job_def_table[modid] = job_defs

    job_overwrites = list(filter(lambda x: len(x[1]) > 1, job_to_modid.items()))
    print('%s job overwrites. ' % len(job_overwrites))

    job_props = set() # job property name for debugging
    all_modifiers = set() # all modifiers name for debugging
    danger_map = {} # danger map for debugging

    mycompat_jobs = [] # all additional job definititons

    all_mod_multid = {} # multiplier value to corresponding script values
    all_mod_multid_rev = {} # reverse lookup of all_mod_multid 

    def get_mod_multid(mult):
        if not mult in all_mod_multid:
            all_mod_multid[mult] = b"MYCOMPAT_agsv_" + str(len(all_mod_multid)).encode()
            all_mod_multid_rev[all_mod_multid[mult]] = mult
        return all_mod_multid[mult]

    for modid, job_defs in job_def_table.items():
        for seg in job_defs:
            jn = seg[0]
            spl = split3(seg[2], inline_option=InlineOption.DoNothing)

            if jn in job_excludes:
                print("manually excluded job detected. Discarding this one.", jn, modid)
                continue

            job_modids = job_to_modid[jn]
            if len(job_modids) > 1:
                _, max_modid = max([calculate_mod_index_from_mod_order(m) for m in job_modids], key=lambda x: x[0])
                if modid == max_modid:
                    print("job overwrite detected: using this mod")
                else:
                    print("job overwrite detected: skip this mod")
                    continue

            # if capped by modifier, change condition to disable it
            # TODO: implement another logic to make use of it (for example, calculate from workshop residue value)
            if get_field(spl, b'is_capped_by_modifier') == b'no':
                add_to_field(seg[2], [b'possible', b'planet'], [b'MYCOMPAT_st_is_enabled', b'=', b'no'], InlineOption.DoNothing)
                print('Overwriting a job that is not capped by modifier ... %s' % jn.decode())
                job_output += export_fields(seg)
                continue
            
            proxyjob_params = [] # proxy job params

            danger = 0 # error value for job

            icon_present = False
            
            # iterate job properties
            for property in spl:
                prop_name = property[0]
                prop_value = property[2]

                # log property name
                job_props.add(prop_name)
            
                match prop_name:
                    case b'overlord_resources' | b'resources':
                        for x in split3(prop_value, InlineOption.DoNothing):
                            match x[0]:
                                case b'produces' | b'upkeep':
                                    if b'multiplier' in x[2]:
                                        val = x[2][x[2].index(b'multiplier') + 2]
                                        x[2][x[2].index(b'multiplier') + 2] = b'value:%s|JOB|%s|' % (get_mod_multid(val), jn)
                                        danger += 1 # be cautious as there's a possibility that the script value won't work
                                    else:
                                        x[2].insert(0, b'planet.value:MYCOMPAT_sv_job_quantity|JOB|%s|' % jn)
                                        x[2].insert(0, b'=')
                                        x[2].insert(0, b'multiplier')
                                case b'category':
                                    pass
                                case x:
                                    print('unsupported resource type %s' % x)
                                    danger += 100000000
                        proxyjob_params += [prop_name, b'=', prop_value]
                    case b'pop_modifier' | b'planet_modifier' | b'country_modifier' | b'triggered_pop_modifier' | b'triggered_planet_modifier' | b'triggered_country_modifier':
                        mult = None
                        potential = None

                        spl_prop_value = split3(prop_value, InlineOption.DoNothing)
                        modifier_field = get_field(spl_prop_value, b'modifier')

                        send = []

                        if modifier_field:
                            spl_prop_value += split3(modifier_field, InlineOption.DoNothing)

                        for mod in spl_prop_value:
                            match mod[0]:
                                case b'modifier':
                                    # reluctant to delete modifier field ...
                                    pass
                                case b'mult' | b'multiplier':
                                    if mult:
                                        print('multiple mult detected in modifiers!!!!', jn, mod[2])
                                        danger += 1000000
                                    mult = mod[2]
                                    print('modifier mult detected: ', jn, mult)
                                    # TODO: implement modifier mult patching more properly (...considering scope difference between pops and triggers? but generally it works very very well :))
                                    danger += 1 # be cautious as there's a possibility that the script value won't work
                                case b'potential':
                                    if potential:
                                        print('multiple potential detected!! using last one', jn)
                                        danger += 1000000
                                    potential = mod[2]
                                case y:
                                    send += mod
                                        
                            all_modifiers.add(mod[0]) # for debug purpose
                        
                        #####
                        
                        if send:
                            send_field_id = b'triggered_' + prop_name if not prop_name.startswith(b'triggered_') else prop_name
                            proxyjob_params += [
                                send_field_id,
                                b'=',
                                [   b'mult',
                                    b'=',
                                    b'planet.value:MYCOMPAT_sv_job_quantity|JOB|%s|' % jn
                                        if not mult else b'value:%s|JOB|%s|' % (get_mod_multid(mult), jn)
                                ] + ([
                                    b'potential',
                                    b'=',
                                    potential
                                ] if potential != None else []) + send
                            ]
                    case _:
                        proxyjob_params += [prop_name, b'=', prop_value]
                        if prop_name == b'icon':
                            icon_present = True
            
            danger_map[jn] = danger

            mycompat_jobs.append(jn)

            deposit_params = [
                b'icon', b'=', b'MYCOMPAT_icon',
                b'is_for_colonizable', b'=', b'yes',
                b'category', b'=', b'MYCOMPAT_cat_job',
                b'should_swap_deposit_on_terraforming', b'=', b'no',
                b'drop_weight', b'=', [ b'weight', b'=', b'0' ],
                b'triggered_planet_modifier', b'=', [
                    b'mult', b'=', b'value:MYCOMPAT_sv_job_count|JOB|%s|' % jn,
                    b'job_%s_add' % jn, b'=', b'-1',
                    b'MYCOMPAT_sm_converted_jobs_add', b'=', b'1'
                ],
                b'planet_modifier', b'=', [
                    b'job_MYCOMPAT_j_%s_add' % jn, b'=', b'1'
                ]
            ]

            deposit_output += export_fields([b'MYCOMPAT_d_%s' % jn, b'=', deposit_params])

            if not icon_present:
                proxyjob_params = [b'icon', b'=', jn] + proxyjob_params

            job_output += export_fields([b'MYCOMPAT_j_%s' % jn, b'=', proxyjob_params])

    for x, y in var_def_table.items():
        job_output = export_fields([x, b'=', y]) + job_output

    danger_jobs = list(filter(lambda x: x[1] > 0, danger_map.items()))

    print(len(danger_jobs), 'dangerous conversion detected')

    with open(patchpath("autogen/danger_jobs.txt"), 'wb') as f:
        for p in sorted(danger_jobs):
            f.write(b'%s %s\n' % (p[0], str(p[1]).encode()))

    with open(patchpath("autogen/processed_jobs.txt"), 'wb') as f:
        for p in sorted(danger_map.keys()):
            f.write(b'%s\n' % p)

    with open(patchpath("autogen/job_props.txt"), 'wb') as f:
        for p in sorted(job_props):
            f.write(p + b'\n')

    with open(patchpath("autogen/all_modifiers.txt"), 'wb') as f:
        for p in sorted(all_modifiers):
            f.write(p + b'\n')

    with open(patchpath("common/pop_jobs/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(job_output)

    with open(patchpath("common/deposits/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(deposit_output)

    scripted_effects_data = [
        b'MYCOMPAT_agse_planet', b'=', 
        list(itertools.chain.from_iterable([b'MYCOMPAT_se_process_job', b'=', [ b'JOB', b'=', x ]] for x in mycompat_jobs))
    ]

    with open(patchpath("common/scripted_effects/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(export_fields(scripted_effects_data))

    for (svid, mult) in all_mod_multid_rev.items():
        sv_output += export_fields([
            svid, b'=', [
                b'base', b'=', b'1',
                b'mult', b'=', b'planet.value:MYCOMPAT_sv_job_quantity|JOB|$JOB$|', #PR_FACTOR_plnt_JOB_
                b'mult', b'=', mult
            ]
        ]) + b'\n'

    with open(patchpath("common/script_values/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(sv_output)

if __name__ == "__main__":
    all_buildings()
    all_jobs()
