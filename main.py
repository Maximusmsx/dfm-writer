import sys


def main():
    if '--self-test' in sys.argv:
        from dfm_writer.selftest import run
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--self-test',required=True)
        parser.add_argument('--live-config')
        parser.add_argument('--live-dfm')
        parser.add_argument('--live-profile',default='lxd')
        args = parser.parse_args()
        return run(args.self_test,args.live_config,args.live_dfm,args.live_profile)
    from PyQt6.QtWidgets import QApplication,QMessageBox
    from dfm_writer.window import MainWindow
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    try:
        window = MainWindow()
    except Exception as error:
        QMessageBox.critical(None,'数据直写DFM启动失败',str(error))
        return 1
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
