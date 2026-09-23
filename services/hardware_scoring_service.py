"""
Hardware Scoring Service for Mythic 3.0.
Calculates provisional and verified scores for Hardware Build Challenge submissions
strictly on the server side using the package's scoring configuration.
"""
from typing import Any


def calculate_hardware_scores(
    submission_data: dict[str, Any],
    rules_config: dict[str, Any],
    scoring_config: dict[str, Any],
    remaining_seconds: int = 0,
    total_duration_seconds: int = 1800,
    is_admin_verified: bool = False,
) -> tuple[float, float, float, dict[str, Any]]:
    """
    Menghitung skor hardware build secara transparan dan deterministik di sisi server.
    Mengembalikan: (raw_score, time_bonus, final_score, score_breakdown)

    Parameter:
    - submission_data: data build yang disubmit (total_price, cpu_score, gpu_score, dll)
    - rules_config: batasan dari paket (max_budget, min_cpu_score, min_gpu_score, dll)
    - scoring_config: konfigurasi bobot penilaian dari paket
    - remaining_seconds: sisa waktu resmi dari server saat submit
    - total_duration_seconds: durasi total sesi pengerjaan
    - is_admin_verified: flag apakah kalkulasi dilakukan atas data terverifikasi panitia
    """
    # 1. Ambil bobot penilaian dari scoring_config paket (default total = 100)
    w_compat = float(scoring_config.get("weight_compatibility", 20.0))
    w_budget = float(scoring_config.get("weight_budget", 15.0))
    w_cpu = float(scoring_config.get("weight_cpu_target", scoring_config.get("weight_cpu", 15.0)))
    w_gpu = float(scoring_config.get("weight_gpu_target", scoring_config.get("weight_gpu", 20.0)))
    w_comp = float(scoring_config.get("weight_completeness", 10.0))
    w_eff = float(scoring_config.get("weight_efficiency", 15.0))
    w_time = float(scoring_config.get("weight_time_bonus", 5.0))

    # 2. Ambil batasan build dari rules_config paket
    max_budget = float(rules_config.get("budget_max", rules_config.get("max_budget", 1500.0)))
    min_cpu_score = float(rules_config.get("min_cpu_score", 1000.0))
    min_gpu_score = float(rules_config.get("min_gpu_score", 2000.0))
    target_efficiency = float(rules_config.get("target_efficiency", 2.0))

    # 3. Data submission
    total_price = float(submission_data.get("total_price") or 0.0)
    cpu_score = float(submission_data.get("cpu_score") or 0.0)
    gpu_score = float(submission_data.get("gpu_score") or 0.0)
    ram_gb = float(submission_data.get("ram_capacity_gb") or 0.0)
    storage_gb = float(submission_data.get("storage_capacity_gb") or 0.0)
    psu_name = str(submission_data.get("psu_name") or "").strip()
    cpu_name = str(submission_data.get("cpu_name") or "").strip()
    gpu_name = str(submission_data.get("gpu_name") or "").strip()

    # Evaluasi Kompatibilitas
    # Jika sudah diverifikasi admin, ikuti penilaian admin.
    # Jika provisional, jika checkbox konfirmasi dicentang dan komponen terisi, dapatkan provisional full.
    if is_admin_verified:
        is_compatible = bool(submission_data.get("is_compatible", True))
    else:
        is_compatible = bool(submission_data.get("confirmation_checked", False))

    compat_score = w_compat if is_compatible else 0.0

    # Evaluasi Budget
    if total_price <= 0:
        budget_score = 0.0
        budget_compliant = False
    elif total_price <= max_budget:
        budget_score = w_budget
        budget_compliant = True
    else:
        # Melebihi budget -> skor budget 0
        budget_score = 0.0
        budget_compliant = False

    # Evaluasi Target CPU
    if min_cpu_score <= 0:
        cpu_achieved_score = w_cpu
        cpu_met = True
    else:
        if cpu_score >= min_cpu_score:
            cpu_achieved_score = w_cpu
            cpu_met = True
        else:
            ratio = max(0.0, cpu_score / min_cpu_score)
            cpu_achieved_score = round(ratio * w_cpu, 2)
            cpu_met = False

    # Evaluasi Target GPU
    if min_gpu_score <= 0:
        gpu_achieved_score = w_gpu
        gpu_met = True
    else:
        if gpu_score >= min_gpu_score:
            gpu_achieved_score = w_gpu
            gpu_met = True
        else:
            ratio = max(0.0, gpu_score / min_gpu_score)
            gpu_achieved_score = round(ratio * w_gpu, 2)
            gpu_met = False

    # Evaluasi Kelengkapan Komponen Wajib (CPU, GPU, RAM, Storage, PSU)
    required_items = [
        bool(cpu_name),
        bool(gpu_name),
        ram_gb > 0,
        storage_gb > 0,
        bool(psu_name),
    ]
    completeness_ratio = sum(1 for item in required_items if item) / len(required_items)
    completeness_score = round(completeness_ratio * w_comp, 2)

    # Evaluasi Efisiensi Harga terhadap Performa
    if total_price > 0 and (cpu_score + gpu_score) > 0:
        eff_ratio = (cpu_score + gpu_score) / total_price
        if target_efficiency > 0:
            eff_score = min(w_eff, round((eff_ratio / target_efficiency) * w_eff, 2))
        else:
            eff_score = w_eff
    else:
        eff_score = 0.0

    # Evaluasi Bonus Waktu (Berdasarkan Waktu Server)
    if remaining_seconds > 0 and total_duration_seconds > 0:
        time_ratio = min(1.0, max(0.0, remaining_seconds / total_duration_seconds))
        time_bonus = round(time_ratio * w_time, 2)
    else:
        time_bonus = 0.0

    # Total Raw Score & Final Score
    raw_score = round(
        compat_score + budget_score + cpu_achieved_score + gpu_achieved_score + completeness_score + eff_score,
        2,
    )
    final_score = min(100.0, round(raw_score + time_bonus, 2))

    breakdown = {
        "compatibility": {
            "weight": w_compat,
            "achieved": compat_score,
            "is_compatible": is_compatible,
        },
        "budget": {
            "weight": w_budget,
            "achieved": budget_score,
            "max_budget": max_budget,
            "total_price": total_price,
            "budget_compliant": budget_compliant,
        },
        "cpu": {
            "weight": w_cpu,
            "achieved": cpu_achieved_score,
            "target": min_cpu_score,
            "submitted": cpu_score,
            "met": cpu_met,
        },
        "gpu": {
            "weight": w_gpu,
            "achieved": gpu_achieved_score,
            "target": min_gpu_score,
            "submitted": gpu_score,
            "met": gpu_met,
        },
        "completeness": {
            "weight": w_comp,
            "achieved": completeness_score,
            "ratio": round(completeness_ratio, 2),
        },
        "efficiency": {
            "weight": w_eff,
            "achieved": eff_score,
            "target_efficiency": target_efficiency,
        },
        "time_bonus": {
            "weight": w_time,
            "achieved": time_bonus,
            "remaining_seconds": remaining_seconds,
            "total_duration_seconds": total_duration_seconds,
        },
        "total_raw": raw_score,
        "final_score": final_score,
        "is_admin_verified": is_admin_verified,
    }

    return raw_score, time_bonus, final_score, breakdown


def calculate_hardware_provisional_score(
    submission_data: dict[str, Any],
    rules_config: dict[str, Any],
    scoring_config: dict[str, Any],
    remaining_seconds: int = 0,
    total_duration_seconds: int = 1800,
) -> tuple[float, float, float, dict[str, Any]]:
    """Menghitung skor provisional hardware di sisi server."""
    return calculate_hardware_scores(
        submission_data,
        rules_config,
        scoring_config,
        remaining_seconds=remaining_seconds,
        total_duration_seconds=total_duration_seconds,
        is_admin_verified=False,
    )


evaluate_hardware_build = calculate_hardware_scores

