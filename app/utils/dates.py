from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621

    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )

    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461

    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365

    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30

    return jy, jm, jd


def _is_gregorian_leap(gy: int) -> bool:
    return gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)


def _is_jalali_leap(jy: int) -> bool:
    a = jy - 474
    b = (a % 2820) + 474
    return ((b + 38) * 682) % 2816 < 682


def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    jy += 1595
    days = -355668 + (365 * jy) + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186

    gy = 400 * (days // 146097)
    days %= 146097

    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1

    gy += 4 * (days // 1461)
    days %= 1461

    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365

    gd = days + 1
    g_d_m = [
        0,
        31,
        29 if _is_gregorian_leap(gy) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    gm = 1
    while gm <= 12 and gd > g_d_m[gm]:
        gd -= g_d_m[gm]
        gm += 1

    return gy, gm, gd


def to_jalali_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value

    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo("Asia/Tehran"))

    jy, jm, jd = _gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d} {dt:%H:%M}"


def jalali_month_days(jy: int, jm: int) -> int:
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if _is_jalali_leap(jy) else 29


def jalali_today(tz: str = "Asia/Tehran") -> tuple[int, int, int]:
    dt = datetime.now(ZoneInfo(tz))
    return _gregorian_to_jalali(dt.year, dt.month, dt.day)


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    return _jalali_to_gregorian(jy, jm, jd)


def to_jalali_month(value: str) -> str:
    try:
        year_str, month_str = value.split("-")
        gy = int(year_str)
        gm = int(month_str)
    except ValueError:
        return value

    jy, jm, _ = _gregorian_to_jalali(gy, gm, 1)
    return f"{jy:04d}/{jm:02d}"
