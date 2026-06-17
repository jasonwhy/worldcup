"""
八卦风控层引擎 —— 电视镜头拍不到的东西
- 纯扣分制：从100分向下扣减
- 更衣室稳定性 + 政治签证干扰 + 球星场外信号
- 时间衰减机制
"""
import json
import math
from datetime import datetime, date
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(name):
    with open(DATA_DIR / name, "r") as f:
        return json.load(f)


def time_decay(event_date_str: str) -> float:
    """时间衰减: 半衰期14天"""
    if not event_date_str:
        return 1.0

    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        days_ago = (date.today() - event_date).days
        if days_ago <= 0:
            return 1.0
        decay = math.exp(-0.05 * days_ago)
        return decay
    except (ValueError, TypeError):
        return 1.0


def clean_stale_gossip():
    """自动清理衰减至<0.1的过期八卦事件"""
    gossip_data = load_json("gossip.json")
    cleaned = {}
    stale_count = 0

    for tid, gdata in gossip_data.items():
        cleaned[tid] = {}
        for section in ["locker_room", "political", "player_off_field"]:
            if section in gdata:
                entry = gdata[section].copy()
                if entry.get("date"):
                    decay = time_decay(entry["date"])
                    if decay < 0.1 and entry.get("score", 0) != 0:
                        entry["score"] = 0
                        entry["reason"] = f"[已过期-自动清零] {entry.get('reason', '')}"
                        stale_count += 1
                cleaned[tid][section] = entry
            else:
                cleaned[tid][section] = {"score": 0, "reason": ""}

    if stale_count > 0:
        import json as _json
        with open(DATA_DIR / "gossip.json", "w") as f:
            _json.dump(cleaned, f, indent=2, ensure_ascii=False)
    return stale_count


def gossip_score(team_id: str) -> dict:
    """
    八卦风控层: 满分100, 向下扣减
    更衣室40% + 政治干扰35% + 球星场外25%
    """
    gossip_data = load_json("gossip.json")
    team_gossip = gossip_data.get(team_id, {})

    base = 100

    # 4.1 更衣室稳定性 (满分8 → 映射到0-40)
    locker = team_gossip.get("locker_room", {})
    locker_deduction = abs(locker.get("score", 0))
    locker_date = locker.get("date", "")
    locker_decay = time_decay(locker_date)
    locker_effective = locker_deduction * locker_decay
    locker_score = max(0, 40 - locker_effective * 5)

    # 4.2 政治/签证干扰 (满分7 → 映射到0-35)
    political = team_gossip.get("political", {})
    pol_deduction = abs(political.get("score", 0))
    pol_score = max(0, 35 - pol_deduction * 5)

    # 4.3 球星场外信号 (满分5 → 映射到0-25)
    player_off = team_gossip.get("player_off_field", {})
    player_deduction = abs(player_off.get("score", 0))
    # 正向信号可以抵消
    positive = player_off.get("positive_signal", "")
    pos_bonus = 2 if positive else 0
    player_score = max(0, min(25, 25 - player_deduction * 5 + pos_bonus))

    final = locker_score + pol_score + player_score

    detail = {
        "locker_room_score": round(locker_score, 1),
        "locker_room_raw": locker.get("score", 0),
        "locker_room_decay": round(locker_decay, 2) if locker.get("date") else None,
        "political_score": round(pol_score, 1),
        "political_level": political.get("level", 0),
        "player_off_field_score": round(player_score, 1),
        "positive_signal": positive if positive else None
    }

    return {"score": round(final, 1), "detail": detail}
