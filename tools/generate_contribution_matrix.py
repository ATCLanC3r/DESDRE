from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "CONTRIBUTION_MATRIX_50_50_DRAFT.pdf"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="MatrixTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#17324D"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
)
styles.add(
    ParagraphStyle(
        name="MatrixHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#17324D"),
        spaceBefore=8,
        spaceAfter=7,
    )
)
styles.add(
    ParagraphStyle(
        name="MatrixBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
    )
)
styles.add(
    ParagraphStyle(
        name="MatrixSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=9.5,
        alignment=TA_LEFT,
    )
)
styles.add(
    ParagraphStyle(
        name="MatrixHeader",
        parent=styles["MatrixSmall"],
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
    )
)
styles.add(
    ParagraphStyle(
        name="MatrixCenter",
        parent=styles["MatrixSmall"],
        alignment=TA_CENTER,
    )
)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7DEE5"))
    canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#5D6B78"))
    canvas.drawString(18 * mm, 8 * mm, "DESD Resit - 50/50 Contribution Matrix Draft")
    canvas.drawRightString(192 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def p(text, style="MatrixBody"):
    return Paragraph(text, styles[style])


story = [
    p("Group Contributions Matrix", "MatrixTitle"),
    p("Bristol Regional Food Network - DESD Resit", "MatrixHeading"),
]

identity = Table(
    [
        [p("Group number"), p("________________"), p("Tutor"), p("________________")],
        [p("Discussion date"), p("________________"), p("Submission date"), p("13 July 2026")],
    ],
    colWidths=[34 * mm, 50 * mm, 34 * mm, 50 * mm],
    rowHeights=[11 * mm, 11 * mm],
)
identity.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF1F7")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EAF1F7")),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#AEBBC7")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]
    )
)
story += [identity, Spacer(1, 8 * mm), p("Group member details", "MatrixHeading")]

members = Table(
    [
        [p("Member", "MatrixHeader"), p("Student ID", "MatrixHeader"), p("Full name", "MatrixHeader"), p("Primary roles", "MatrixHeader")],
        [p("1"), p("[enter ID]"), p("Chi Miu"), p("Backend, database, Docker, testing, documentation")],
        [p("2"), p("[enter ID]"), p("Abdullah"), p("Backend, frontend, API, testing, project management")],
    ],
    colWidths=[18 * mm, 35 * mm, 48 * mm, 67 * mm],
    rowHeights=[10 * mm, 16 * mm, 16 * mm],
)
members.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#AEBBC7")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]
    )
)
story += [members, Spacer(1, 7 * mm), p("Overall contribution summary", "MatrixHeading")]

overall = Table(
    [
        [p("Member", "MatrixHeader"), p("Contribution", "MatrixHeader"), p("Evidence-based justification", "MatrixHeader")],
        [p("Chi Miu"), p("50%"), p("Completed 10 of 20 exclusively owned technical components: requirements/project management, database, Django models, authentication, authorisation, sessions, security, Docker, multi-container architecture, and Git evidence.", "MatrixSmall")],
        [p("Abdullah"), p("50%"), p("Completed 10 of 20 exclusively owned technical components: views/controllers, frontend, forms/validation, CRUD, external services, media storage, debugging, performance, UI/UX, and REST API.", "MatrixSmall")],
        [p("Total"), p("100%"), p("Both members confirm that this split matches the actual resit-period evidence.", "MatrixSmall")],
    ],
    colWidths=[28 * mm, 28 * mm, 112 * mm],
    rowHeights=[10 * mm, 23 * mm, 23 * mm, 15 * mm],
)
overall.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF6EE")),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#AEBBC7")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]
    )
)
story += [overall, Spacer(1, 6 * mm), p("Draft status", "MatrixHeading")]
story += [
    p(
        "This document records a 50/50 overall split using exclusive task ownership: Chi Miu owns 10 technical components and Abdullah owns 10. Each row is 100/0, not 50/50. Add student IDs, evidence references, and discussion details before signing."
    ),
    PageBreak(),
    p("Technical component contributions", "MatrixTitle"),
]

components = [
    ("Requirements analysis, documentation, and project management", "Chi Miu"),
    ("Database schema design and implementation", "Chi Miu"),
    ("Django model classes development", "Chi Miu"),
    ("Views and controllers implementation", "Abdullah"),
    ("Template design and frontend development", "Abdullah"),
    ("Form handling and data validation", "Abdullah"),
    ("User authentication system", "Chi Miu"),
    ("User authorisation and permissions", "Chi Miu"),
    ("Session management implementation", "Chi Miu"),
    ("CRUD operations development", "Abdullah"),
    ("External services integration", "Abdullah"),
    ("Cloud/local media storage implementation", "Abdullah"),
    ("Security features implementation", "Chi Miu"),
    ("Docker containerisation setup", "Chi Miu"),
    ("Docker multi-container architecture", "Chi Miu"),
    ("Bug fixes and system debugging", "Abdullah"),
    ("Performance optimisation and reliability", "Abdullah"),
    ("User interface and user experience", "Abdullah"),
    ("REST API development", "Abdullah"),
    ("Git management and evidence", "Chi Miu"),
]

component_rows = [[p("Technical component", "MatrixHeader"), p("Chi Miu", "MatrixHeader"), p("Abdullah", "MatrixHeader"), p("Total", "MatrixHeader")]]
for component, owner in components:
    chi_percent = "100%" if owner == "Chi Miu" else "0%"
    abdullah_percent = "100%" if owner == "Abdullah" else "0%"
    component_rows.append([p(component, "MatrixSmall"), p(chi_percent, "MatrixCenter"), p(abdullah_percent, "MatrixCenter"), p("100%", "MatrixCenter")])

component_table = Table(
    component_rows,
    colWidths=[105 * mm, 22 * mm, 22 * mm, 19 * mm],
    rowHeights=[9 * mm] + [10.3 * mm] * len(components),
    repeatRows=1,
)
component_style = [
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#AEBBC7")),
    ("INNERGRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#D7DEE5")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
]
for row in range(2, len(component_rows), 2):
    component_style.append(("BACKGROUND", (0, row), (-1, row), colors.HexColor("#F5F8FA")))
component_table.setStyle(TableStyle(component_style))
story += [component_table, PageBreak(), p("Agreement and verification", "MatrixTitle")]

checks = [
    "[ ] We reviewed the Git commit history for both members.",
    "[ ] We reviewed the Notion task pages and evidence links.",
    "[ ] We discussed time investment and workload distribution.",
    "[ ] Both members understand and can demonstrate the submitted code.",
    "[ ] Chi Miu owns 10 components and Abdullah owns 10 components.",
    "[ ] Every technical component has exactly one owner (100/0).",
    "[ ] The generative-AI declaration is accurate and follows module guidance.",
]
story += [p("Verification checklist", "MatrixHeading")]
for check in checks:
    story += [p(check), Spacer(1, 2.2 * mm)]

story += [Spacer(1, 4 * mm), p("Discussion record", "MatrixHeading")]
discussion = Table(
    [
        [p("Date of contribution discussion"), p("________________________________________")],
        [p("Meeting duration"), p("________________________________________")],
        [p("Both members present"), p("Yes / No")],
        [p("Disagreements"), p("Yes / No")],
        [p("Resolution, if required"), p("________________________________________<br/>________________________________________")],
    ],
    colWidths=[60 * mm, 108 * mm],
    rowHeights=[12 * mm, 12 * mm, 12 * mm, 12 * mm, 25 * mm],
)
discussion.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF1F7")),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#AEBBC7")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]
    )
)
story += [discussion, Spacer(1, 8 * mm), p("Group consensus declaration", "MatrixHeading")]
story += [
    p(
        "We confirm that the final contribution percentages have been discussed, are supported by evidence, and accurately reflect each member's contribution. We understand that these percentages may affect individual marks."
    ),
    Spacer(1, 10 * mm),
]

signatures = Table(
    [
        [p("Chi Miu signature"), p("____________________________"), p("Date"), p("____________")],
        [p("Abdullah signature"), p("____________________________"), p("Date"), p("____________")],
    ],
    colWidths=[38 * mm, 70 * mm, 20 * mm, 40 * mm],
    rowHeights=[16 * mm, 16 * mm],
)
signatures.setStyle(
    TableStyle(
        [
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#AEBBC7")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]
    )
)
story += [signatures]

doc = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    rightMargin=18 * mm,
    leftMargin=18 * mm,
    topMargin=16 * mm,
    bottomMargin=18 * mm,
    title="DESD Resit 50/50 Contribution Matrix Draft",
    author="DESD Resit Group",
)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUTPUT)
