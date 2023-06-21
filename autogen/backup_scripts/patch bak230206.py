import os

import glob

import re

import itertools

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
    get all txt files under game_path/modid/cat/*.txt and parse them. (glob wildcard accepted)

    Set simple=True to switch to simple mode.
    complex mode is default.

    simple mode ... each segments in top-level must be in format 'segment_name = { ... }', not 'segment_name = segment_value'.
        otherwise the latter one will be regarded as a comment!
        useful in top-level file parsing.
        keeps comments and other rubbish data except at end of a file.
        thus, each segment ends with }
        but the beginning of each segment may be whitespace, tab, newline or '#'.
    complex mode ... parse each item as a nested list structure. support statements like 'a = b' in top-level
        dispose all comments
        each item will be parsed as a list which consists of a property name bytes, b'=', a property value bytes, or another list (which means another level of data within { ... })
    """
    if simple:
        f = get_segments_simple
    else:
        f = get_segments_complex
    return list(itertools.chain.from_iterable(map(f, get_scripts_from_category(game_path, modid, cat))))

def get_scripts(game_path, modid, query):
    return list(glob.glob(os.path.join(game_path, modid, query)))

def get_segments_complex(scr):
    comment = False
    current_ptr = []
    parent_ptrs = []
    result = current_ptr
    separation = False
    
    for char in scr:
        char = char.to_bytes(1)
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
                    if x == b'=':
                        separation = True
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

def split3(target):
    """
    Splits target into a list of length-3 lists.
    Asserts that `len(target) % 3 == 0` and the middle element of each list is `b'='`
    Useful for additional parsing after finishing complex mode parsing
    """
    assert len(target) % 3 == 0
    out = [target[i:i+3] for i in range(0, len(target), 3)]
    assert all([x[1] == b'=' for x in out])
    return out

def get_segments_simple(scr):
    result = []
    first_bracket_arrived = False
    comment = False
    nest = 0
    segment = b""
    for char in scr:
        char = char.to_bytes(1)
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
                r = b"PR_trgr_plnt_HC_MORE = { HC = %s }" % str(int(m.group(2))).encode()
            case b'<=':
                r = b"PR_trgr_plnt_HC_LESS = { HC = %s }" % str(int(m.group(2)) + 1).encode()
            case b'>':
                r = b"PR_trgr_plnt_HC_MORE = { HC = %s }" % str(int(m.group(2)) + 1).encode()
            case b'<':
                r = b"PR_trgr_plnt_HC_LESS = { HC = %s }" % str(int(m.group(2))).encode()
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

#######
#
# Indivisual scripts for mods
#
#######

aot_modid = "2178603631" # Acquisition of Technologies modid
mr_modid = "2807759164" # Merger of Rules modid

# aot

def aot():
    ss = get_segments_from_category(stellaris_path, aot_modid, "common/buildings", simple=True)
    
    with open(patchpath("common/buildings/あ自動生成aot_patch.txt"), "wb") as f:
        for s in ss:
            result = num_pops_patch(s)
            if result:
                f.write(result + b"\n")

# mr

def mr():
    ss = get_segments_from_category(stellaris_path, mr_modid, "common/scripted_triggers", simple=True)

    regularcode = list(filter(lambda x: re.match(rb'^\s*is_regular_empire\s*=\s*{', x), ss))[0]

    regularcode = regularcode.replace(b"is_country_type = default", b"is_country_type = default\n\t\tis_country_type = original_empire_active", 1)

    with open(patchpath("common/scripted_triggers/あ自動生成mr_patch.txt"), "wb") as f:
        f.write(regularcode)

# all_jobs

prpatch_modid = '2830366252'
pr_modid = '2529002857'
aup_modid = '1995601384'
st_modid = '688086068'
sw_modid = '2583755721'

mod_excludes = [prpatch_modid, pr_modid, aup_modid, st_modid, sw_modid]

def all_jobs():
    output_data = b''

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

    props = set()
    for modid, job_defs in job_def_table.items():
        for seg in job_defs:
            jn = seg[0]
            spl = split3(seg[2])

            changed = False

            if get_field(spl, b'is_capped_by_modifier') == b'no':
                print('Found a job that is not capped by modifier: %s' % jn.decode())
                if len(job_to_modid[jn]) > 1:
                    raise NotImplementedError('conflict solver is not implemented yet')
                print('replacing possible field...')
                add_to_field(seg[2], [b'possible', b'planet'], [b'PR_trgr_plnt_REG', b'=', b'no'])
                changed = True
            
            if changed:
                print('Writing job %s ...' % jn.decode())
            
            for x in spl:
                props.add(x[0])

    print('job properties: ', *[p.decode() for p in props])

    # planet_modifier
    # country_modifier
    # triggered_planet_modifier
    # resources
    # triggered_pop_modifier
    # triggered_country_modifier
    # pop_modifier 

    # is_capped_by_modifier


if __name__ == "__main__":
    stellaris_path = "C:/Program Files (x86)/Steam/steamapps/workshop/content/281990/"
    all_jobs()
