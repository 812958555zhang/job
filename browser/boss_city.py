"""
BOSS 直聘城市编码解析与页面切换
"""

import asyncio
import re
from typing import Any, Optional

from utils.logger import get_logger

_logger = get_logger(__name__)

COMMON_CITY_CODES = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "武汉": "101200100",
    "成都": "101270100",
    "南京": "101190100",
    "西安": "101110100",
    "苏州": "101190400",
    "天津": "101030100",
    "重庆": "101040100",
    "长沙": "101250100",
    "郑州": "101180100",
    "青岛": "101120200",
    "厦门": "101230200",
    "合肥": "101220100",
    "宁波": "101210400",
    "东莞": "101281600",
    "佛山": "101280800",
    "全国": "100010000",
}

_FETCH_CITY_CODE_JS = """
async (targetName) => {
  const normalize = (name) => {
    if (!name) return '';
    return String(name).trim().replace(/(市|省|自治区|特别行政区)$/g, '');
  };
  const target = normalize(targetName);
  if (!target) return null;
  const matchName = (name) => {
    const n = normalize(name);
    return n === target || n.includes(target) || target.includes(n);
  };
  const tryList = (list) => {
    if (!Array.isArray(list)) return null;
    for (const item of list) {
      if (item && matchName(item.name) && item.code) return String(item.code);
      const sub = item && item.subLevelModelList;
      if (Array.isArray(sub)) {
        for (const child of sub) {
          if (child && matchName(child.name) && child.code) return String(child.code);
        }
      }
    }
    return null;
  };
  try {
    const resp = await fetch('/wapi/zpCommon/data/city.json', { credentials: 'include' });
    if (!resp.ok) return null;
    const payload = await resp.json();
    const zp = payload && payload.zpData;
    if (!zp) return null;
    return tryList(zp.hotCityList) || tryList(zp.cityList) || null;
  } catch (e) {
    return null;
  }
}
"""

_SWITCH_CITY_JS = """
async (targetCity) => {
  const normalize = (name) => String(name || '').trim().replace(/(市|省|自治区|特别行政区)$/g, '');
  const target = normalize(targetCity);
  if (!target) return { ok: false, reason: 'empty_target' };
  const bodyText = document.body ? document.body.innerText : '';
  const currentMatch = bodyText.match(/([\\u4e00-\\u9fff]{2,6})\\[切换\\]/);
  if (currentMatch && normalize(currentMatch[1]) === target) {
    return { ok: true, action: 'already', city: currentMatch[1] };
  }
  const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  const clickSwitch = () => {
    for (const el of document.querySelectorAll('a, span, div, button, i')) {
      const text = (el.innerText || '').trim();
      if (!text || !isVisible(el)) continue;
      if (text === '切换' || text.endsWith('[切换]') || text.includes('切换')) {
        el.click();
        return true;
      }
    }
    return false;
  };
  if (!clickSwitch()) return { ok: false, reason: 'switch_button_not_found' };
  await new Promise((r) => setTimeout(r, 900));
  for (const el of document.querySelectorAll('li, span, div, a, p, dd')) {
    const text = (el.innerText || '').trim();
    if (!text || !isVisible(el)) continue;
    if (text === target || text === target + '市' || normalize(text) === target) {
      el.click();
      await new Promise((r) => setTimeout(r, 1800));
      return { ok: true, action: 'switched', city: text };
    }
  }
  return { ok: false, reason: 'city_option_not_found' };
}
"""


def normalize_city_name(name: str) -> str:
    name = (name or "").strip()
    return re.sub(r"(市|省|自治区|特别行政区)$", "", name)


def lookup_city_code(city_name: str) -> Optional[str]:
    normalized = normalize_city_name(city_name)
    if not normalized:
        return None
    if normalized in COMMON_CITY_CODES:
        return COMMON_CITY_CODES[normalized]
    for key, code in COMMON_CITY_CODES.items():
        if key in normalized or normalized in key:
            return code
    return None


def cities_match(left: str, right: str) -> bool:
    a = normalize_city_name(left)
    b = normalize_city_name(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def detect_city_from_page_text(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"([\u4e00-\u9fff]{2,6})\[切换\]", text)
    return match.group(1) if match else None


async def resolve_city_code(page: Any, city_name: str) -> Optional[str]:
    code = lookup_city_code(city_name)
    if code:
        return code
    if page is None or not hasattr(page, "evaluate"):
        return None
    try:
        result = await page.evaluate(_FETCH_CITY_CODE_JS, city_name)
        return str(result) if result else None
    except Exception as exc:
        _logger.warning("通过 city.json 解析城市失败 (%s): %s", city_name, exc)
        return None


async def _switch_city_via_playwright(page: Any, target_city: str) -> bool:
    target = normalize_city_name(target_city)
    if not target or not hasattr(page, "locator"):
        return False
    for sel in ("text=切换", ".switch-city", '[class*="switch-city"]'):
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click(timeout=4000)
                await asyncio.sleep(0.9)
                break
        except Exception:
            continue
    else:
        return False
    for name in (target, f"{target}市"):
        try:
            option = page.get_by_text(name, exact=True).first
            if await option.count() > 0 and await option.is_visible():
                await option.click(timeout=5000)
                await asyncio.sleep(1.8)
                return True
        except Exception:
            continue
    return False


async def ensure_boss_search_city(
    page: Any,
    target_city_name: str,
    city_code: Optional[str] = None,
) -> bool:
    from browser.agent_helpers import extract_page_text

    if page is None or not target_city_name:
        return False

    current = None
    try:
        sample = await extract_page_text(page, max_chars=800)
        current = detect_city_from_page_text(sample)
        if current and cities_match(current, target_city_name):
            _logger.info("搜索页城市已是: %s", current)
            return True
    except Exception as exc:
        _logger.debug("读取当前城市失败: %s", exc)

    _logger.info("正在通过页面切换城市: %s → %s", current or "未知", target_city_name)

    switched = False
    if hasattr(page, "locator"):
        try:
            switched = await _switch_city_via_playwright(page, target_city_name)
        except Exception as exc:
            _logger.debug("Playwright 切换城市失败: %s", exc)

    if not switched and hasattr(page, "evaluate"):
        try:
            result = await page.evaluate(_SWITCH_CITY_JS, target_city_name)
            switched = bool(result and result.get("ok"))
            if switched:
                _logger.info("页面城市切换完成: %s", (result or {}).get("city") or target_city_name)
            elif result:
                _logger.warning("页面城市切换失败: %s", result.get("reason"))
        except Exception as exc:
            _logger.warning("JS 切换城市失败: %s", exc)

    if not switched and city_code and hasattr(page, "goto"):
        try:
            new_url = re.sub(r"city=[^&]+", f"city={city_code}", page.url)
            if new_url == page.url and "city=" not in page.url:
                sep = "&" if "?" in page.url else "?"
                new_url = f"{page.url}{sep}city={city_code}"
            await page.goto(new_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
            sample = await extract_page_text(page, max_chars=800)
            current = detect_city_from_page_text(sample)
            switched = bool(current and cities_match(current, target_city_name))
        except Exception as exc:
            _logger.debug("URL 重载切换城市失败: %s", exc)

    return switched
