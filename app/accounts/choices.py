import datetime


FOUNDING_YEAR = 1995

# 与学校 2026 年公布的教学科研单位名称保持一致，避免同一学院出现多种简称。
COLLEGE_CHOICES = [
    ("船舶工程学院", "船舶工程学院"),
    ("航空航天学院", "航空航天学院"),
    ("动力与能源工程学院", "动力与能源工程学院"),
    ("智能科学与工程学院", "智能科学与工程学院"),
    ("水声工程学院", "水声工程学院"),
    ("计算机科学与技术学院", "计算机科学与技术学院"),
    ("国家保密学院", "国家保密学院"),
    ("国家特色化示范性软件学院", "国家特色化示范性软件学院"),
    ("机电工程学院", "机电工程学院"),
    ("信息与通信工程学院", "信息与通信工程学院"),
    ("集成电路学院", "集成电路学院"),
    ("经济管理学院", "经济管理学院"),
    ("材料科学与化学工程学院", "材料科学与化学工程学院"),
    ("数学科学学院", "数学科学学院"),
    ("物理与光电工程学院", "物理与光电工程学院"),
    ("外国语学院", "外国语学院"),
    ("人文社会科学学院", "人文社会科学学院"),
    ("核科学与技术学院", "核科学与技术学院"),
    ("马克思主义学院", "马克思主义学院"),
    ("国际合作教育学院", "国际合作教育学院"),
    ("中外联合学院", "中外联合学院"),
    ("未来技术学院", "未来技术学院"),
]


def cohort_choices() -> list[tuple[str, str]]:
    year = datetime.date.today().year
    return [(str(value), f"{value} 级") for value in range(year, FOUNDING_YEAR - 1, -1)]


def position_term_choices() -> list[tuple[int, str]]:
    year = datetime.date.today().year
    return [(value, f"{value}-{value + 1} 届") for value in range(year + 1, FOUNDING_YEAR - 1, -1)]


def position_term_label(year) -> str:
    return f"{year}-{year + 1} 届" if year is not None else "届次待补充"
