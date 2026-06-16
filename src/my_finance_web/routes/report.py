import os
import shutil
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file, url_for

from ..config import _QUARTO_PDF, _SEND_SCRIPT, _get_email_config, _proj_dir

report_bp = Blueprint("report", __name__)


def _pdf_exists():
    return _QUARTO_PDF.exists()


@report_bp.route("/api/generate_report")
def generate_report():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    day = request.args.get("day", type=int)
    if not all([year, month, day]):
        return jsonify({"success": False, "error": "缺少日期参数 year/month/day"}), 400

    qmd_template = Path("/home/song/NutstoreFiles/projects/PrettyDoc/reports/SiKuReport/daily_report/daily_report_account-gb.qmd")
    if not qmd_template.exists():
        return jsonify({"success": False, "error": "日报模板文件不存在"}), 400

    output_dir = _proj_dir / "generated_reports"
    output_dir.mkdir(exist_ok=True)

    report_basename = f"daily_report_{year}{month:02d}{day:02d}"

    cmd = [
        "micromamba", "run", "-n", "quarto", "bash", "-c",
        f"export PYTHONPATH=/home/song/NutstoreFiles/2-Code/1-MyPython/pybox:${{PYTHONPATH:-}} && cd /home/song/NutstoreFiles/projects/PrettyDoc && quarto render reports/SiKuReport/daily_report/daily_report_account-gb.qmd -P year:{year} -P month:{month} -P day:{day}"
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        quarto_pdf = Path("/home/song/NutstoreFiles/projects/PrettyDoc/_output/reports/SiKuReport/daily_report/daily_report_account-gb.pdf")
        if not quarto_pdf.exists():
            raise FileNotFoundError("PDF 生成失败，quarto 未输出文件")
        dest_pdf = output_dir / (report_basename + ".pdf")
        shutil.copy(quarto_pdf, dest_pdf)
        quarto_docx = Path("/home/song/NutstoreFiles/projects/PrettyDoc/_output/reports/SiKuReport/daily_report/daily_report_account-gb.docx")
        if quarto_docx.exists():
            shutil.copy(quarto_docx, output_dir / (report_basename + ".docx"))
        download_url = url_for("report.download_report", filename=dest_pdf.name)
        return jsonify({"success": True, "url": download_url})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": e.stderr}), 500


@report_bp.route("/download_report/<filename>")
def download_report(filename):
    file_path = _proj_dir / "generated_reports" / filename
    if not file_path.exists():
        return "文件不存在", 404
    return send_file(file_path, as_attachment=True)


@report_bp.route("/api/send_report")
def send_report():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    day = request.args.get("day", type=int)
    if not all([year, month, day]):
        return jsonify({"success": False, "error": "缺少日期参数 year/month/day"}), 400

    generated = False
    if not _pdf_exists():
        qmd_template = Path("/home/song/NutstoreFiles/projects/PrettyDoc/reports/SiKuReport/daily_report/daily_report_account-gb.qmd")
        if not qmd_template.exists():
            return jsonify({"success": False, "error": "日报模板文件不存在"}), 400

        output_dir = _proj_dir / "generated_reports"
        output_dir.mkdir(exist_ok=True)
        report_basename = f"daily_report_{year}{month:02d}{day:02d}"

        cmd = [
            "micromamba", "run", "-n", "quarto", "bash", "-c",
            f"export PYTHONPATH=/home/song/NutstoreFiles/2-Code/1-MyPython/pybox:${{PYTHONPATH:-}} && cd /home/song/NutstoreFiles/projects/PrettyDoc && quarto render reports/SiKuReport/daily_report/daily_report_account-gb.qmd -P year:{year} -P month:{month} -P day:{day}"
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            quarto_pdf = _QUARTO_PDF
            if not quarto_pdf.exists():
                raise FileNotFoundError("PDF 生成失败，quarto 未输出文件")
            dest_pdf = output_dir / (report_basename + ".pdf")
            shutil.copy(quarto_pdf, dest_pdf)
            quarto_docx = Path("/home/song/NutstoreFiles/projects/PrettyDoc/_output/reports/SiKuReport/daily_report/daily_report_account-gb.docx")
            if quarto_docx.exists():
                shutil.copy(quarto_docx, output_dir / (report_basename + ".docx"))
            generated = True
        except subprocess.CalledProcessError as e:
            return jsonify({"success": False, "error": e.stderr}), 500
        except FileNotFoundError as e:
            return jsonify({"success": False, "error": str(e)}), 500

    try:
        email_cfg = _get_email_config()
        env = os.environ.copy()
        if email_cfg.get("from"):
            env["EMAIL_FROM"] = email_cfg["from"]
        if email_cfg.get("to"):
            env["EMAIL_TO"] = email_cfg["to"]
        if email_cfg.get("subject_prefix"):
            env["EMAIL_SUBJECT_PREFIX"] = email_cfg["subject_prefix"]
        result = subprocess.run(
            ["bash", str(_SEND_SCRIPT), "--send-only"],
            capture_output=True, text=True, check=True,
            env=env,
        )
        return jsonify({
            "success": True,
            "generated": generated,
            "to": email_cfg.get("to", ""),
            "message": result.stdout.strip() if result.stdout else "",
        })
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": e.stderr or "邮件发送失败"}), 500
