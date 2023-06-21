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
                r = b"PR_prmt_trgr_plnt_HC = { MORE = %s }" % str(int(m.group(2)) - 1).encode()
            case b'<=':
                r = b"PR_prmt_trgr_plnt_HC = { LESS = %s }" % str(int(m.group(2)) + 1).encode()
            case b'>':
                r = b"PR_prmt_trgr_plnt_HC = { MORE = %s }" % str(int(m.group(2))).encode()
            case b'<':
                r = b"PR_prmt_trgr_plnt_HC = { LESS = %s }" % str(int(m.group(2))).encode()
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

# mr
"""
this part of code is broken ;(

def mr():
    ss = get_segments_from_category(stellaris_path, mr_modid, "common/scripted_triggers", simple=True)

    regularcode = list(filter(lambda x: re.match(rb'^\s*is_regular_empire\s*=\s*{', x), ss))[0]

    regularcode = regularcode.replace(b"is_country_type = default", b"is_country_type = default\n\t\tis_country_type = original_empire_active", 1)

    with open(patchpath("common/scripted_triggers/%smr_patch.txt" % file_prefix), "wb") as f:
        f.write(regularcode)
"""


def all_jobs():
    """
    ALL JOBS PATCH!
    """

    """
    =============================================
     Figure out PRPATCH & PR registration status
    =============================================
    deposits PR_D_JOB_<job name>
    scripted_effects PR_eft_plnt_JOB_deposit_<mod abb name>
    """

    exist_d = set() # We'll use deposit as canonical job registration
    exist_e = set()

    job_to_modabb = {}

    prpatch_d = split3(get_segments_from_category(stellaris_path, prpatch_modid, "common/deposits", simple=False))
    prpatch_d += split3(get_segments_from_category(stellaris_path, pr_modid, "common/deposits", simple=False))

    for seg in prpatch_d:
        m = re.match(rb'PR_D_JOB_(.+)', seg[0])
        if m:
            jobname = m[1]
            exist_d.add(jobname)
        else:
            print('unsupported deposit name', seg[0])

    prpatch_e = split3(get_segments_from_category(stellaris_path, prpatch_modid, "common/scripted_effects", simple=False))
    prpatch_e += split3(get_segments_from_category(stellaris_path, pr_modid, "common/scripted_effects", simple=False))

    for seg in prpatch_e:
        m = re.match(rb'PR_eft_plnt_JOB_deposit_(.+)', seg[0])
        if m:
            abb = m[1]
            ifblock = get_field_after(seg[2], rb'if')
            if ifblock == None:
                ifblock = seg[2][1:] # for vanilla one, "if" block does not exist
                # raise NotImplementedError('PR effect lookup failed', m[0])
            ifblock = split3(ifblock)
            for x in ifblock:
                if x[0] == rb'PR_prmt_eft_plnt_JOB_deposit_DB':
                    jobname = get_field(split3(x[2]), rb'JOB')
                    if jobname == None:
                        raise NotImplementedError('PR effect jobname lookup failed', m[0])
                    exist_e.add(jobname)
                    job_to_modabb[jobname] = abb
        else:
            print('unsupported scripted effect', seg[0])

    print('deposit - effect = ', exist_d - exist_e)

    print('effect - deposit = ', exist_e - exist_d)

    """
    ===========================
     Figure out Job Categories
    ===========================
    """

    prpatch_m = split3(get_segments_from_category(stellaris_path, prpatch_modid, "common/scripted_modifiers", simple=False))
    prpatch_m += split3(get_segments_from_category(stellaris_path, pr_modid, "common/scripted_modifiers", simple=False))

    exist_smod_cat_keys = set()

    for seg in prpatch_m:
        m = re.match(rb'PR_smod_plnt_CAT_(.+)_add', seg[0])
        if m:
            exist_smod_cat_keys.add(m[0])
        else:
            print('unsupported scripted modifier', seg[0])

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

    for modid in os.listdir(stellaris_path):
        if os.path.isdir(os.path.join(stellaris_path, modid)):
            print('processing modid ', modid)

            if modid in mod_excludes:
                print(" .... skipping this mod")
                continue

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

    job_props = set()
    all_modifiers = set()
    danger_map = {}
    mycompat_jobs = []
    all_smod_cat_keys = set()
    all_pomod = set()
    all_comod = set()

    all_mod_multid = {}
    all_mod_multid_rev = {}

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
                if not jn in mod_order:
                    print("Conflict detected! \n please update mod_order in config.py! \n [[[Original dict]]] \n %s \n Please choose ONE modid (as a string) from each entry in the given dict, and overwrite the entry value with the modid." % dict(filter(lambda x: len(x[1])>1, job_to_modid.items())))
                    sys.exit()
                if modid != mod_order[jn]:
                    print("job overwrite detected. Discarding this one.", jn, modid)
                    continue
                else:
                    print("job overwrite detected. Using this one.", jn, modid)

            # if capped by modifier, change condition to disable it
            # TODO: implement another logic to make use of it (for example, calculate from workshop value)
            if get_field(spl, b'is_capped_by_modifier') == b'no':
                add_to_field(seg[2], [b'possible', b'planet'], [b'PR_trgr_plnt_REG', b'=', b'no'])
                print('Overwriting a job that is not capped by modifier ... %s' % jn.decode())
                job_output += export_fields(seg)
                continue
            
            deposit_params = []

            danger = 0
            
            # iterate job properties
            for property in spl:
                prop_name = property[0]
                prop_value = property[2]

                # log property name
                job_props.add(prop_name)
            
                # TODO: implement overlord_resources (maybe not that hard)
                match prop_name:
                    case b'resources':
                        for x in split3(prop_value):
                            match x[0]:
                                case b'category':
                                    jobcat = x[2]
                                case b'produces' | b'upkeep':
                                    if b'multiplier' in x[2]:
                                        val = x[2][x[2].index(b'multiplier') + 2]
                                        eff = b'general'

                                        # TODO: implement workaround for unsupported things (same as modifier multiplier, use sv)
                                        if giga_modid in job_to_modid[jn] and val == b'10':
                                            eff = b'giga_ten'
                                        elif giga_modid in job_to_modid[jn] and val == b'planet.value:giga_job_scaling_plus_base':
                                            eff = b'giga_scaling_plus_base'
                                        else:
                                            print('unsupported multiplier detected in resources', val, jn, job_to_modid[jn])
                                            danger += 100
                                        x[2][x[2].index(b'multiplier') + 2] = b'value:PR_prmt_sv_plnt_JOB_FACTOR|JOB|%s|EFFICIENCY|%s|' % (jn, eff)
                                    else:
                                        x[2].insert(0, b'value:PR_prmt_sv_plnt_JOB_FACTOR|JOB|%s|EFFICIENCY|general|' % jn)
                                        x[2].insert(0, b'=')
                                        x[2].insert(0, b'multiplier')
                                case x:
                                    print('unsupported resource type %s', x)
                                    # TODO: implement fcking INLINE SCRIPTS!!!! (for vanillas only? but all vanila scripts should be patched anyway...)
                                    danger += 100000000
                                    #raise NotImplementedError('unsupported resource type %s', x)  
                        deposit_params += [prop_name, b'=', prop_value]
                    case b'pop_modifier' | b'planet_modifier' | b'country_modifier' | b'triggered_pop_modifier' | b'triggered_planet_modifier' | b'triggered_country_modifier':
                        mult = None # should be None, otherwise something went wrong
                        potential = None
                        send_planet = [] # modifiers that are sent to "triggered_planet_modifier"

                        spl_prop_value = split3(prop_value)
                        modifier_field = get_field(spl_prop_value, b'modifier')

                        if modifier_field:
                            spl_prop_value += split3(modifier_field)

                        for mod in spl_prop_value:
                            match mod[0]:
                                case b'modifier':
                                    pass
                                case b'mult' | b'multiplier':
                                    if mult:
                                        print('multiple mult detected in modifiers!!!!', jn, mod[2])
                                        danger += 1000000
                                    match mod[2]:
                                        case b'value:scripted_modifier_mult|MODIFIER|pop_job_trade_mult|':
                                            pass
                                        case b'value:scripted_modifier_mult|MODIFIER|pop_job_amenities_mult|':
                                            pass
                                        case y:
                                            mult = y
                                            print('modifier mult detected: ', jn, mult)
                                            # TODO: implement modifier mult patching more properly (...considering scope difference between pops and triggers)
                                            danger += 1 # be cautious as there's a possibility that the script value won't work
                                case b'potential':
                                    if potential:
                                        print('multiple potential detected!! using last one', jn)
                                        danger += 1000000
                                    potential = mod[2]
                                case b'country_naval_cap_add': # country mod template?
                                    send_planet += [b'PR_smod_plnt_MOD_naval_cap_add', b'=', mod[2]]
                                case b'pop_defense_armies_add': # pop mod template?
                                    send_planet += [b'PR_smod_plnt_MOD_defense_armies_add', b'=', mod[2]]
                                case b'trade_value_add': # planet mod template?
                                    send_planet += [b'PR_smod_plnt_MOD_trade_value_add', b'=', mod[2]]
                                case b'planet_amenities_add' | b'planet_amenities_no_happiness_add': # planet mod template?
                                    send_planet += [b'PR_smod_plnt_MOD_all_amenities_add', b'=', mod[2]]
                                case y:
                                    if prop_name.endswith(b'planet_modifier'):
                                        send_planet += mod
                                    elif prop_name.endswith(b'pop_modifier'):
                                        print('pop modifier detected!!!!!', prop_name, jn, y)
                                        # TODO: uncommment here after implementing POMOD function
                                        # send_planet += [b'mycompat_POMOD_' + mod[0], mod[1], mod[2]]
                                        # all_pomod.add(b'mycompat_POMOD_' + mod[0])
                                        danger += 10000
                                    elif prop_name.endswith(b'country_modifier'):
                                        print('country modifier detected!!!!!', prop_name, jn, y)
                                        send_planet += [b'mycompat_COMOD_' + mod[0], mod[1], mod[2]]
                                        all_comod.add(b'mycompat_COMOD_' + mod[0])
                                        
                            all_modifiers.add(mod[0])
                        
                        #####
                        
                        if send_planet:
                            deposit_params += [
                                b'triggered_planet_modifier',
                                b'=',
                                [   b'mult',
                                    b'=',
                                    b'value:PR_prmt_sv_plnt_JOB_FACTOR|JOB|%s|' % jn
                                        if not mult else b'value:%s|JOB|%s|' % (get_mod_multid(mult), jn)
                                ] + ([
                                    b'potential',
                                    b'=',
                                    potential
                                ] if potential != None else []) + send_planet]
            
            danger_map[jn] = danger

            if jn in job_to_modabb:
                abbkey = job_to_modabb[jn]
            else:
                abbkey = b'MYCOMPAT'
                mycompat_jobs.append(jn)
            
            smod_cat_key = b'PR_smod_plnt_CAT_%s_add' % jobcat

            all_smod_cat_keys.add(smod_cat_key)

            deposit_params = [
                b'icon', b'=', b'PR_D_icon_MOD',
                b'is_for_colonizable', b'=', b'yes',
                b'category', b'=', b'PR_D_cat_JOB',
                b'should_swap_deposit_on_terraforming', b'=', b'no',
                b'drop_weight', b'=', [ b'weight', b'=', b'0' ],
                b'planet_modifier', b'=', [
                    b'PR_smod_plnt_JOB_deposit_%s' % abbkey, b'=', b'1'
                ],
                b'triggered_planet_modifier', b'=', [
                    b'mult', b'=', b'value:PR_prmt_sv_plnt_JOB_FACTOR|JOB|%s|' % jn,
                    b'job_%s_add' % jn, b'=', b'-1',
                    b'PR_smod_plnt_VAR_workshop_add', b'=', b'1',
                    smod_cat_key, b'=', b'1',
                ]
            ] + deposit_params

            deposit_output += export_fields([b'PR_D_JOB_%s' % jn, b'=', deposit_params])

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
    
    """
    pr_segments = split3(get_segments_from_category(stellaris_path, pr_modid, "common/pop_jobs", simple=False))
    pr_core_job = next(filter(lambda x: x[0] == b'PR_job_CORE_regular', pr_segments))
    # TODO: also implement pomod (pop modifier)! calculating ratio of the job to the entire workshop might help.
    for modname in all_comod:
        modname_orig = modname.split(b'mycompat_COMOD_')[1]
        pr_core_job[2] += [b'triggered_country_modifier', b'=', [
            b'potential', b'=', [
                b'planet', b'=', [
                    b'check_modifier_value', b'=', [
                        b'modifier', b'=', modname,
                        b'value', b'!=', b'0'
                    ]
                ]
            ],
            b'mult', b'=', b'planet.modifier:%s' % modname,
            modname_orig, b'=', b'1'
        ]]
    job_output += export_fields(pr_core_job)
    """

    with open(patchpath("common/pop_jobs/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(job_output)

    with open(patchpath("common/deposits/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(deposit_output)

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

    for (svid, mult) in all_mod_multid_rev.items():
        sv_output += export_fields([
            svid, b'=', [
                b'base', b'=', b'1', b'mult', b'=', b'PR_FACTOR_plnt_JOB_$JOB$', 
                b'mult', b'=', mult
            ]
        ]) + b'\n'

    with open(patchpath("common/script_values/%sall_jobs_patch.txt" % file_prefix), 'wb') as f:
        f.write(sv_output)

if __name__ == "__main__":
    
    aot()
    # mr()
    all_jobs()
