from access_it.common.text import normalize_string_and_fold_case


def is_this_organization_excluded(name: str | None) -> bool:
    if name is None:
        return False
    excluded = False
    excluding_patterns = [
        "elite",
        "el a ", "el à ", "el-o", "el+o", "el.o", "el/o",
        "open ",
        "open-", "open - ", "op-",
        "open+", "open + ", "op+",
        "open/", "open / ", "op/",
        "open1", "open 1",
        "open2", "open 2",
        "open3", "open 3",
        "op1", "op2", "op3",
        "op ", "op1", "op2", "op3",
        "u7", "u8", "u9", "u10", "u11", "u12",
        "u13", "u14", "u15", "u16", "u17",
        "u 7", "u 8", "u 9", "u 10", "u 11", "u 12",
        "u 13", "u 14", "u 15", "u 16", "u 17",
    ]
    n = normalize_string_and_fold_case(name)
    for exc in excluding_patterns:
        excluded = excluded or (n.find(exc) != -1)
    return excluded


def is_this_organization_included(name: str | None) -> bool:
    if name is None:
        return False
    included = False
    including_patterns = [
        "access", "acess", "acces", "accce", "acc",
        "a1", "a2", "a3", "a4"
    ]
    n = normalize_string_and_fold_case(name)
    for inc in including_patterns:
        included = included or (n.find(inc) != -1)
    return included
