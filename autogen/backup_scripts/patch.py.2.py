import os

import glob

import re

import itertools

#######
#
# UTIL functions
#
#######

def get_scripts_from_category(game_path, modid, cat):
    paths = get_scripts(game_path, modid, "common/%s/*.txt" % cat)
    result = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            result.append(f.read())
    return result

# simple ... each segments must be in format 'segment_name = { ... }', not 'segment_name = segment_value'
#   useful in top-level file parsing.
#   keeps comments and other rubbish data except at end of a file.
#   thus, each segment ends with }
#   but the start of each segment may be whitespace, tab, newline or '#'.
# complex ... parses name and contents of each items. support statements like 'a = b' in top-level
#   dispose comments before, after, and between items (but keeps comments within an item)
#   each segments will be parsed as a pair (name, value)
def get_segments_from_category(game_path, modid, cat, simple=False):
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
    for char in scr:
        match char:
            case '{':
                if not comment:
                    parent_ptrs.append(current_ptr)
                    x = []
                    current_ptr[-1][1] = x
                    current_ptr = x
            case '}':
                if not comment:
                    current_ptr = parent_ptrs.pop()
            case '#':
                comment = True
            case '\n' | '\r' | ' ' | '\t' | '\f' | '\v':
                if char == '\n' or char == '\r':
                    comment = False
                if comment == False:
                    if len(current_ptr) > 0 and current_ptr[-1][1] != None:
                        assert isinstance(current_ptr[-1][1], str)
                        current_ptr.append([None, None])
            case '=':
                if not comment:
                    assert isinstance(current_ptr[-1][0], str)
                    current_ptr[-1][1] = ''
            case x:
                if not comment:
                    if current_ptr[-1][0] == None:
                        current_ptr[-1][0] = ''
                    else:
                        current_ptr[-1][1] = ''
    
    return result

def get_segments_simple(scr):
    result = []
    first_bracket_arrived = False
    comment = False
    nest = 0
    segment = ""
    for char in scr:
        match char:
            case '{':
                if not comment:
                    nest += 1
                    first_bracket_arrived = True
            case '}':
                if not comment:
                    nest -= 1
            case '#':
                comment = True
            case '\n':
                comment = False
        segment += char
        if first_bracket_arrived and nest == 0:
            result.append(segment)
            segment = ""
            first_bracket_arrived = False
    return result

def num_pops_patch(segment):
    def repfunc(m):
        match m.group(1):
            case '>=':
                r = "PR_trgr_plnt_HC_MORE = { HC = %s }" % m.group(2)
            case '<=':
                r = "PR_trgr_plnt_HC_LESS = { HC = %s }" % int(m.group(2)) + 1
            case '>':
                r = "PR_trgr_plnt_HC_MORE = { HC = %s }" % int(m.group(2)) + 1
            case '<':
                r = "PR_trgr_plnt_HC_LESS = { HC = %s }" % m.group(2)
        return r
    if "num_pops" in segment:
        replaced = re.sub(r"num_pops\s*(>=|<=|>|<)\s*(.+)", repfunc, segment)
        if replaced == segment:
            print("WARNING !!! unsupported num_pops expression !!!")
            return None
        return replaced
    else:
        return None

def patchpath(p):
    return os.path.join(os.path.dirname(__file__), "../", p)

def dig_segment(segment):
    # 1. separate name and contents
    m = re.search(r'^\s*([^#\s]+)\s*=\s*\{(.*)\}(.*)', segment, re.MULTILINE | re.DOTALL)
    assert m[3] == ''
    return (m[1], m[2])



#######
#
# Indivisual scripts for mods
#
#######

aot_modid = "2178603631" # Acquisition of Technologies modid
mr_modid = "2807759164" # Merger of Rules modid

# aot

def aot():
    ss = get_segments_from_category(stellaris_path, aot_modid, "buildings", simple=True)
    
    with open(patchpath("common/buildings/あ自動生成aot_patch.txt"), "w") as f:
        for s in ss:
            result = num_pops_patch(s)
            if result:
                f.write(result + "\n")

# mr

def mr():
    ss = get_segments_from_category(stellaris_path, mr_modid, "scripted_triggers", simple=True)

    regularcode = list(filter(lambda x: re.match(r'^\s*is_regular_empire\s*=\s*{', x), ss))[0]

    regularcode = regularcode.replace("is_country_type = default", "is_country_type = default\n\t\tis_country_type = original_empire_active", 1)

    with open(patchpath("common/scripted_triggers/あ自動生成mr_patch.txt"), "w") as f:
        f.write(regularcode)

# all_jobs

prpatch_modid = '2830366252'

def all_jobs():
    all_segments = get_segments_from_category(stellaris_path, "*", "pop_jobs", simple=False)
    print('%s segments found' % len(all_segments))

    jobnames = [re.search(r'^\s*([^#\s]+)\s*=\s*{', x, re.MULTILINE)[1] for x in all_segments]
    print('%s job names found' % len(jobnames))
    jobnames_set = list(set(jobnames))
    print('%s unique job names found' % len(jobnames_set))

    # jobnames_sorted = sorted(jobnames)
    # jobnames_duplicates = list(filter(lambda x: jobnames_sorted[x[0]-1] == jobnames_sorted[x[0]] if x != 0 else False, enumerate(jobnames_sorted)))
    # print('%s conflicting job definitions found' % len(jobnames_duplicates))

def test_all():
    all_segments = get_segments_from_category(stellaris_path, "*", "*", simple=False)
    

if __name__ == "__main__":
    stellaris_path = "C:/Program Files (x86)/Steam/steamapps/workshop/content/281990/"
    # all_jobs()
    test_all()

