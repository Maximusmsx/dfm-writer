"""Create the project's small application icon with native Qt drawing."""
from pathlib import Path
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage,QPainter,QColor,QFont,QPen,QFontDatabase
from PyQt6.QtCore import Qt,QRectF


def main():
    app = QApplication.instance() or QApplication([])
    if not QFontDatabase.families():
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeuib.ttf'))
    image = QImage(256,256,QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#225dc0'))
    painter.drawRoundedRect(QRectF(8,8,240,240),48,48)
    painter.setBrush(QColor('#ffffff'))
    painter.drawRoundedRect(QRectF(47,36,162,188),12,12)
    painter.setPen(QColor('#225dc0'))
    painter.setFont(QFont('Segoe UI',31,QFont.Weight.Bold))
    painter.drawText(QRectF(47,76,162,70),Qt.AlignmentFlag.AlignCenter,'DFM')
    painter.setPen(QPen(QColor('#5b95e8'),9,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    painter.drawLine(77,165,177,165)
    painter.drawLine(77,185,143,185)
    painter.end()
    assets = Path(__file__).resolve().parent/'assets'
    assets.mkdir(exist_ok=True)
    image.save(str(assets/'dfm.png'))
    # Windows ICO supports a PNG image payload; no extra imaging dependency is needed.
    import struct
    payload = (assets/'dfm.png').read_bytes()
    (assets/'dfm.ico').write_bytes(struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',0,0,0,0,1,32,len(payload),22)+payload)


if __name__ == '__main__':
    main()
