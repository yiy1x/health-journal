import datetime
import hashlib
import random

from .validation import ALLERGENS, AppError, boolean, choice, date_value, text


RECIPES = [
    {"id": "b1", "meal": "breakfast", "name": "燕麦牛奶碗 · 香蕉", "ingredients": ["原味燕麦 40 g", "无添加牛奶 200 ml", "香蕉半根"], "allergens": ["牛奶", "小麦"], "vegetarian": True, "minutes": 8, "color": "oat", "method": "燕麦加水煮软，拌入牛奶，放上香蕉。燕麦按可能含麸质保守标注。"},
    {"id": "b2", "meal": "breakfast", "name": "小米粥 · 鸡蛋 · 苹果", "ingredients": ["小米 40 g（干重）", "鸡蛋 1 个", "苹果半个"], "allergens": ["鸡蛋"], "vegetarian": True, "minutes": 20, "color": "gold", "method": "小米煮粥，鸡蛋煮熟，水果洗净切块；不额外加糖。"},
    {"id": "b3", "meal": "breakfast", "name": "蒸红薯 · 原味豆浆", "ingredients": ["红薯 150 g", "原味豆浆 250 ml", "小番茄 100 g"], "allergens": ["大豆"], "vegetarian": True, "minutes": 20, "color": "rose", "method": "红薯蒸熟，搭配彻底煮熟的豆浆和小番茄。豆浆配料只含黄豆和水。"},
    {"id": "b4", "meal": "breakfast", "name": "南瓜粥 · 白豆拌黄瓜", "ingredients": ["大米 35 g（干重）", "南瓜 100 g", "熟白豆 80 g", "黄瓜 100 g"], "allergens": [], "vegetarian": True, "minutes": 25, "color": "gold", "method": "南瓜与大米煮粥；使用充分煮熟的白豆，与黄瓜拌匀，不用预制沙拉酱。"},
    {"id": "l1", "meal": "lunch", "name": "香菇鸡肉饭 · 西兰花", "ingredients": ["大米 70 g（干重）", "鸡肉 100 g", "香菇 80 g", "西兰花 150 g"], "allergens": [], "vegetarian": False, "minutes": 25, "color": "green", "method": "鸡肉和香菇用少量植物油炒熟，搭配米饭与焯熟的西兰花；仅以少量盐调味，不用酱油。"},
    {"id": "l2", "meal": "lunch", "name": "番茄豆腐饭 · 时蔬", "ingredients": ["糙米与大米共 70 g（干重）", "原味豆腐 150 g", "番茄 150 g", "青菜 150 g"], "allergens": ["大豆"], "vegetarian": True, "minutes": 25, "color": "rose", "method": "米饭煮熟，番茄炖豆腐，青菜炒熟；仅用少量植物油和盐。"},
    {"id": "l3", "meal": "lunch", "name": "清蒸鱼 · 杂粮饭", "ingredients": ["大米与小米共 70 g（干重）", "鱼肉 100 g", "胡萝卜 80 g", "青菜 180 g"], "allergens": ["鱼"], "vegetarian": False, "minutes": 25, "color": "blue", "method": "鱼肉去刺、加姜蒸至熟透；配杂粮饭和熟蔬菜。不使用蒸鱼豉油。"},
    {"id": "l4", "meal": "lunch", "name": "鹰嘴豆蔬菜饭", "ingredients": ["大米 65 g（干重）", "熟鹰嘴豆 100 g", "胡萝卜 100 g", "西葫芦 150 g"], "allergens": [], "vegetarian": True, "minutes": 20, "color": "gold", "method": "使用充分煮熟的鹰嘴豆，与熟蔬菜及米饭搭配；不用预制复合调味料。"},
    {"id": "d1", "meal": "dinner", "name": "冬瓜鸡肉汤 · 米饭", "ingredients": ["鸡肉 100 g", "冬瓜 200 g", "大米 60 g（干重）", "青菜 150 g"], "allergens": [], "vegetarian": False, "minutes": 30, "color": "green", "method": "鸡肉和冬瓜煮至熟透，搭配米饭和熟青菜。清水煮汤，不用复合汤料。"},
    {"id": "d2", "meal": "dinner", "name": "南瓜蒸蛋 · 小米饭", "ingredients": ["鸡蛋 1 个", "南瓜 150 g", "大米与小米共 60 g（干重）", "西兰花 180 g"], "allergens": ["鸡蛋"], "vegetarian": True, "minutes": 25, "color": "gold", "method": "南瓜与蛋液蒸至熟透，米饭及蔬菜分别煮熟；可按食欲适量调整。"},
    {"id": "d3", "meal": "dinner", "name": "鲜虾蔬菜面", "ingredients": ["原味小麦面条 70 g（干重）", "虾仁 100 g", "青菜 150 g", "蘑菇 100 g"], "allergens": ["小麦", "甲壳类"], "vegetarian": False, "minutes": 15, "color": "rose", "method": "面条、虾仁和蔬菜煮熟；核对面条配料，不使用额外酱料。"},
    {"id": "d4", "meal": "dinner", "name": "土豆白豆煲 · 青菜", "ingredients": ["土豆 180 g", "熟白豆 100 g", "番茄 120 g", "青菜 180 g"], "allergens": [], "vegetarian": True, "minutes": 25, "color": "green", "method": "土豆、番茄与熟白豆炖熟，配熟青菜。白豆须充分煮熟。"},
]
BY_ID = {recipe["id"]: recipe for recipe in RECIPES}
MEALS = ("breakfast", "lunch", "dinner")
NOTICE = "一般成人家常餐单灵感，不是治疗性食谱。份量仅为示例，未计算营养素或个体能量需求。请核对食材包装、复合配料和交叉接触风险；有严重过敏或医学饮食需求时请咨询专业人员。"


def restrictions(profile, records):
    reasons = []
    if profile["diet"] == "unspecified":
        reasons.append("请先在设置中选择饮食偏好，不会替你默认选择")
    if not profile["diet_acknowledged"]:
        reasons.append("请先在设置中确认：用于一般成人膳食灵感，已核对过敏与特殊饮食需求")
    if profile["clinical_diet"] or profile["diet_notes"].strip():
        reasons.append("你记录了特殊饮食需求或医嘱；当前版本不自动制定治疗性餐单")
    if profile["birth_date"]:
        born = datetime.date.fromisoformat(profile["birth_date"])
        today = datetime.date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age < 18:
            reasons.append("当前餐单只适用于一般成人，不为未成年人自动规划")
    unknown = set(profile["allergies"]) - set(ALLERGENS)
    if unknown:
        reasons.append("菜谱库无法可靠识别这些过敏原：" + "、".join(sorted(unknown)))
    caution = ("肾", "糖尿病", "心力衰竭", "心衰", "肝硬化", "痛风", "高尿酸", "吞咽", "妊娠", "怀孕", "营养不良")
    for record in records:
        if record["kind"] == "condition" and record["data"]["status"] == "confirmed" and any(word in record["title"] for word in caution):
            reasons.append("档案中有需个别评估的健康问题：" + record["title"])
    return reasons


def eligible(recipe, profile):
    return not set(recipe["allergens"]) & set(profile["allergies"]) and (profile["diet"] != "vegetarian" or recipe["vegetarian"])


def make_plan(day, profile, records, revision=0):
    day = date_value(day, "餐单日期", True)
    reasons = restrictions(profile, records)
    if reasons:
        raise AppError("；".join(reasons), 422)
    if type(revision) is not int or revision < 0 or revision > 100000:
        raise AppError("餐单版本无效")
    seed = hashlib.sha256((day + str(revision) + str(sorted(profile["allergies"])) + profile["diet"]).encode()).hexdigest()
    generator = random.Random(seed)
    selections = {}
    for meal in MEALS:
        candidates = [recipe for recipe in RECIPES if recipe["meal"] == meal and eligible(recipe, profile)]
        if not candidates:
            raise AppError("没有能满足已知限制的" + {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}[meal] + "菜谱，请人工规划", 422)
        selections[meal] = {"recipe_id": generator.choice(candidates)["id"], "eaten": False, "note": ""}
    return {"date": day, "revision": revision, "meals": selections, "constraints": {"allergies": profile["allergies"], "diet": profile["diet"]}, "notice": NOTICE}


def validate_plan(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("meals"), dict):
        raise AppError("餐单格式无效")
    day = date_value(raw.get("date", ""), "餐单日期", True)
    meals = {}
    for meal in MEALS:
        entry = raw["meals"].get(meal)
        if not isinstance(entry, dict) or not isinstance(entry.get("recipe_id"), str) or entry["recipe_id"] not in BY_ID or BY_ID[entry["recipe_id"]]["meal"] != meal:
            raise AppError("餐单包含不存在或类型错误的菜谱")
        meals[meal] = {"recipe_id": entry["recipe_id"], "eaten": boolean(entry.get("eaten", False), "用餐状态"), "note": text(entry.get("note", ""), "实际饮食备注", 1000)}
    constraints = raw.get("constraints", {})
    if not isinstance(constraints, dict) or not isinstance(constraints.get("allergies", []), list):
        raise AppError("餐单约束格式无效")
    allergies = constraints.get("allergies", [])
    if len(allergies) > 20:
        raise AppError("餐单过敏原过多")
    revision = raw.get("revision", 0)
    if type(revision) is not int or not 0 <= revision <= 100000:
        raise AppError("餐单版本无效")
    return {"date": day, "revision": revision, "meals": meals, "constraints": {"allergies": [text(item, "过敏原", 40, True) for item in allergies], "diet": choice(constraints.get("diet", "balanced"), ("balanced", "vegetarian"), "饮食偏好")}, "notice": NOTICE}
