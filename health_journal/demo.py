import datetime

from .nutrition import make_plan
from .store import DEFAULT_PROFILE
from .validation import AppError


def seed_demo(store):
    if store.setting("demo"):
        return
    with store.connection() as database:
        if database.execute("SELECT COUNT(*) FROM wearable_samples").fetchone()[0]:
            raise AppError("已有个人设备样本，不能混入演示资料")
        if database.execute("SELECT COUNT(*) FROM food_entries").fetchone()[0]:
            raise AppError("已有个人饮食日记，不能混入演示资料")
    if store.records() or store.documents() or store.plans() or store.analyses() or store.profile() != DEFAULT_PROFILE:
        raise AppError("演示数据只能加载到新的独立目录，不会混入已有档案")
    today = datetime.date.today()
    def day(offset):
        return (today + datetime.timedelta(days=offset)).isoformat()
    store.profile({"name": "体验档案", "birth_date": "1992-06-15", "sex": "unspecified", "allergies": [], "diet": "balanced", "diet_acknowledged": True, "notes": "此档案完全由程序生成，所有记录均为虚构演示，不属于任何真实患者。"})
    report = "合成演示资料 — 非真实病历\n\n本文件只用于展示来源追溯，不用于医疗判断。\n检测机构：示例健康中心（同一演示方法）。\n"
    for offset, value in [(-120, 3.6), (-90, 3.3), (-60, 3.4), (-30, 3.0), (-7, 2.9)]:
        report += day(offset) + " 低密度脂蛋白胆固醇：" + str(value) + " mmol/L，演示参考区间 0–3.4。\n"
    report += "\n" + day(-7) + " 体检就诊：整理既往报告，讨论常规随访。无临床诊断结论。\n"
    document = store.add_document("合成演示_检验与就诊摘录.txt", report.encode("utf-8"))
    for offset, value in [(-120, 3.6), (-90, 3.3), (-60, 3.4), (-30, 3.0), (-7, 2.9)]:
        store.save_record({"kind": "observation", "title": "低密度脂蛋白胆固醇", "date": day(offset), "department": "体检中心", "topic": "年度体检", "source_label": "合成演示文件，数值虚构", "document_id": document["id"], "verification": "verified", "data": {"value": value, "unit": "mmol/L", "reference_low": 0, "reference_high": 3.4, "lab": "示例健康中心 / 演示方法"}})
    store.save_record({"kind": "visit", "title": "年度体检结果复阅", "date": day(-7), "department": "全科", "topic": "年度体检", "verification": "verified", "document_id": document["id"], "source_label": "合成演示文件", "data": {"hospital": "示例健康中心", "doctor": "示例医生", "reason": "整理体检记录，准备常规随访", "conclusion": "合成演示：仅讨论资料整理，无诊断或治疗结论。"}})
    store.save_record({"kind": "visit", "title": "口腔常规检查", "date": day(-22), "department": "口腔科", "topic": "口腔护理", "source_label": "虚构就诊，未附原件", "data": {"hospital": "示例口腔门诊", "reason": "记录一次常规检查"}})
    store.save_record({"kind": "symptom", "title": "久坐后的肩颈不适", "date": day(-2), "department": "个人记录", "topic": "日常感受", "source_label": "合成自述", "notes": "演示记录，不用于判断原因。", "data": {"severity": 3, "duration": "间歇出现", "triggers": "久坐后注意到，活动后的变化待观察", "status": "ongoing"}})
    store.save_record({"kind": "condition", "title": "肩颈不适原因待查", "date": day(-2), "department": "全科", "topic": "日常感受", "source_label": "合成自述，不是诊断", "data": {"status": "suspected"}})
    store.save_record({"kind": "reminder", "title": "整理报告，准备复诊问题", "date": day(3), "department": "全科", "topic": "年度体检", "notes": "提醒时间为演示安排，不是医疗建议。", "data": {"category": "followup", "done": False}})
    store.save_record({"kind": "reminder", "title": "补录口腔检查原件", "date": day(7), "department": "口腔科", "topic": "口腔护理", "data": {"category": "other", "done": False}})
    store.save_plan(make_plan(day(0), store.profile(), store.records()))
    store.set_setting("demo", True)
