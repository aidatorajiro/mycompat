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

def get_scripts_from_category(game_path, modid, cat, with_modid=False):
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

# TODO: implement inline script
def process_inline(spl):
    inlines = list(filter(lambda x: x[0] == b'inline_script', spl))
    if len(inlines) > 0:
        print("WARNING!!!! unprocessed inline script!!!!!!!")
        return list(filter(lambda x: x[0] != b'inline_script', spl))
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

def split3(target):
    """
    Splits target into a list of length-3 lists.\n
    Asserts that `len(target) % 3 == 0` and the middle element of each list is '=' or ''!=' or '>=' and so on.\n
    Useful for additional parsing after finishing complex mode parsing
    """
    assert len(target) % 3 == 0
    out = [target[i:i+3] for i in range(0, len(target), 3)]
    assert all([is_eq_like(x[1]) for x in out])
    return process_inline(out)

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

def num_pops_patch(segment):
    def repfunc(m):
        match m.group(1):
            case b'>=':
                r = b"MYCOMPAT_totalpop = { MORE = %s }" % str(int(m.group(2)) - 1).encode()
            case b'<=':
                r = b"MYCOMPAT_totalpop = { LESS = %s }" % str(int(m.group(2)) + 1).encode()
            case b'>':
                r = b"MYCOMPAT_totalpop = { MORE = %s }" % str(int(m.group(2))).encode()
            case b'<':
                r = b"MYCOMPAT_totalpop = { LESS = %s }" % str(int(m.group(2))).encode()
        return r
    if b"num_pops" in segment:
        replaced = re.sub(rb"num_pops\s*(>=|<=|>|<)\s*(\d+)", repfunc, segment)
        if b"num_pops" in replaced:
            raise NotImplementedError("WARNING !!! unsupported num_pops expression !!!")
        return replaced
    else:
        return None

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

def add_to_field(target, path, contents):
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
        spl = split3(target)
        field = get_field(spl, path[0])
        if field == None:
            obj = [path[0], b'=', []]
            target += obj
            spl.append(obj)
            field = obj[2]
        add_to_field(field, path[1:], contents)

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


#######
#
# Indivisual scripts for mods
#
#######


# aot

def aot():
    ss = get_segments_from_category(stellaris_path, aot_modid, "common/buildings", simple=True)
    
    with open(patchpath("common/buildings/%saot_patch.txt" % file_prefix), "wb") as f:
        for s in ss:
            result = num_pops_patch(s)
            if result:
                f.write(result + b"\n")

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

    for modid in ['v'] + os.listdir(stellaris_path):
        if modid == 'v' or os.path.isdir(os.path.join(stellaris_path, modid)):
            print('processing modid ', modid)

            if modid in mod_excludes:
                print(" .... skipping this mod")
                continue

            if modid == 'v':
                all_segments = split3(get_segments_from_category(stellaris_game_path, '.', "common/pop_jobs", simple=False))
            else:
                all_segments = split3(get_segments_from_category(stellaris_path, modid, "common/pop_jobs", simple=False))

            job_defs = list(filter(lambda x: isinstance(x[2], list), all_segments))

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
            all_mod_multid[mult] = b"mycompat_agsv_" + str(len(all_mod_multid)).encode()
            all_mod_multid_rev[all_mod_multid[mult]] = mult
        return all_mod_multid[mult]

    for modid, job_defs in job_def_table.items():
        for seg in job_defs:
            jn = seg[0]
            spl = split3(seg[2])

            job_modids = job_to_modid[jn]
            if len(job_modids) > 1:
                if 'v' in job_modids and len(job_modids) == 2:
                    if modid == 'v':
                        print("job overwrite detected. Discarding this one.", jn, modid)
                        continue
                    else:
                        print("job overwrite detected. Using this one.", jn, modid)
                else:
                    if not jn in mod_order:
                        print("Conflict detected! \n please update mod_order in config.py! \n [[[Original dict]]] \n %s \n Please choose ONE modid (as a string) from each entry in the given dict, and overwrite the entry value with the modid." % dict(filter(lambda x: len(x[1])>1, job_to_modid.items())))
                        sys.exit()
                    if modid != mod_order[jn]:
                        print("job overwrite detected. Discarding this one.", jn, modid)
                        continue
                    else:
                        print("job overwrite detected. Using this one.", jn, modid)

            # if capped by modifier, change condition to disable it
            # TODO: implement another logic to make use of it (for example, calculate from workshop residue value)
            if get_field(spl, b'is_capped_by_modifier') == b'no':
                add_to_field(seg[2], [b'possible', b'planet'], [b'MYCOMPAT_is_enabled', b'=', b'no'])
                print('Overwriting a job that is not capped by modifier ... %s' % jn.decode())
                job_output += export_fields(seg)
                continue
            
            agjob_params = [] # aggregated job params

            danger = 0 # error value for job
            
            # iterate job properties
            for property in spl:
                prop_name = property[0]
                prop_value = property[2]

                # log property name
                job_props.add(prop_name)
            
                # TODO: implement overlord_resources (maybe not that hard)
                match prop_name:
                    case b'overlord_resources' | b'resources':
                        for x in split3(prop_value):
                            match x[0]:
                                case b'produces' | b'upkeep':
                                    if b'multiplier' in x[2]:
                                        val = x[2][x[2].index(b'multiplier') + 2]
                                        x[2][x[2].index(b'multiplier') + 2] = b'value:%s|JOB|%s|' % (get_mod_multid(val), jn)
                                        danger += 1 # be cautious as there's a possibility that the script value won't work
                                    else:
                                        x[2].insert(0, b'value:MYCOMPAT_job_efficiency|JOB|%s|' % jn)
                                        x[2].insert(0, b'=')
                                        x[2].insert(0, b'multiplier')
                                case b'category':
                                    pass
                                case x:
                                    print('unsupported resource type %s' % x)
                                    danger += 100000000
                        agjob_params += [prop_name, b'=', prop_value]
                    case b'pop_modifier' | b'planet_modifier' | b'country_modifier' | b'triggered_pop_modifier' | b'triggered_planet_modifier' | b'triggered_country_modifier':
                        mult = None
                        potential = None

                        spl_prop_value = split3(prop_value)
                        modifier_field = get_field(spl_prop_value, b'modifier')

                        send = []

                        if modifier_field:
                            spl_prop_value += split3(modifier_field)

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
                            agjob_params += [
                                send_field_id,
                                b'=',
                                [   b'mult',
                                    b'=',
                                    b'value:MYCOMPAT_job_efficiency|JOB|%s|' % jn
                                        if not mult else b'value:%s|JOB|%s|' % (get_mod_multid(mult), jn)
                                ] + ([
                                    b'potential',
                                    b'=',
                                    potential
                                ] if potential != None else []) + send
                            ]
            
            danger_map[jn] = danger

            mycompat_jobs.append(jn)

            deposit_params = [
                b'icon', b'=', b'MYCOMPAT_icon',
                b'is_for_colonizable', b'=', b'yes',
                b'category', b'=', b'MYCOMPAT_cat_job',
                b'should_swap_deposit_on_terraforming', b'=', b'no',
                b'drop_weight', b'=', [ b'weight', b'=', b'0' ],
                b'triggered_planet_modifier', b'=', [
                    b'mult', b'=', b'value:MYCOMPAT_job_efficiency|JOB|%s|' % jn,
                    b'job_%s_add' % jn, b'=', b'-1',
                    b'MYCOMPAT_job_availability_add', b'=', b'1',
                ]
            ]

            deposit_output += export_fields([b'MYCOMPAT_JD_%s' % jn, b'=', deposit_params])

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

    """
    scripted_effects_data = [
        b'PR_eft_plnt_JOB_deposit_MYCOMPAT', b'=', [
            b'if', b'=', [
                b'limit', b'=', [ b'OR', b'=', [
                    b'check_modifier_value', b'=', [ b'modifier', b'=', b'PR_smod_plnt_JOB_deposit_MYCOMPAT', b'value', b'>', b'0' ],
                    b'exists', b'=', b'owner'
                ]]
            ] + list(itertools.chain.from_iterable([b'PR_prmt_eft_plnt_JOB_deposit_DB', b'=', [ b'JOB', b'=', x ]] for x in mycompat_jobs))
        ]
    ]

    with open(patchpath("common/scripted_effects/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(export_fields(scripted_effects_data))

    with open(patchpath("common/scripted_modifiers/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        for x in (all_smod_cat_keys - exist_smod_cat_keys).union(all_pomod).union(all_comod):
            f.write(b'%s = { icon = mod_PR_smod_plnt_JOB_deposit_V_regular good = yes category = planet}\n' % x)
    """

    for (svid, mult) in all_mod_multid_rev.items():
        sv_output += export_fields([
            svid, b'=', [
                b'base', b'=', b'1', b'mult', b'=', b'MYCOMPAT_job_factor_$JOB$', #PR_FACTOR_plnt_JOB_
                b'mult', b'=', mult
            ]
        ]) + b'\n'

    with open(patchpath("common/script_values/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(sv_output)

if __name__ == "__main__":
    
    aot()
    # mr()
    all_jobs()
