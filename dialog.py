# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'dialog.ui'
#
# Created by: PyQt5 UI code generator 5.15.6
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(459, 310)
        self.geniusToken = QtWidgets.QLineEdit(Dialog)
        self.geniusToken.setGeometry(QtCore.QRect(10, 50, 431, 36))
        self.geniusToken.setObjectName("geniusToken")
        self.saveConfigButton = QtWidgets.QPushButton(Dialog)
        self.saveConfigButton.setGeometry(QtCore.QRect(330, 260, 107, 38))
        self.saveConfigButton.setObjectName("saveConfigButton")
        self.label = QtWidgets.QLabel(Dialog)
        self.label.setGeometry(QtCore.QRect(10, 20, 431, 22))
        self.label.setOpenExternalLinks(True)
        self.label.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        self.label.setObjectName("label")
        self.lastFmUsername = QtWidgets.QLineEdit(Dialog)
        self.lastFmUsername.setGeometry(QtCore.QRect(10, 150, 431, 36))
        self.lastFmUsername.setObjectName("lastFmUsername")
        self.label_3 = QtWidgets.QLabel(Dialog)
        self.label_3.setGeometry(QtCore.QRect(10, 190, 291, 16))
        self.label_3.setObjectName("label_3")
        self.lastFmPassword = QtWidgets.QLineEdit(Dialog)
        self.lastFmPassword.setGeometry(QtCore.QRect(10, 210, 431, 36))
        self.lastFmPassword.setObjectName("lastFmPassword")
        self.label_2 = QtWidgets.QLabel(Dialog)
        self.label_2.setGeometry(QtCore.QRect(10, 120, 431, 22))
        self.label_2.setOpenExternalLinks(True)
        self.label_2.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        self.label_2.setObjectName("label_2")

        self.retranslateUi(Dialog)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "Dialog"))
        self.saveConfigButton.setText(_translate("Dialog", "Save"))
        self.label.setText(_translate("Dialog", "Genius token (can be get here: <a href=\"https://genius.com/api-clients\">genius.com/api-clients</a>"))
        self.label_3.setText(_translate("Dialog", "LastFM Password"))
        self.label_2.setText(_translate("Dialog", "<html><head/><body><p>LastFM Username</p></body></html>"))
