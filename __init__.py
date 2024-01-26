import os
import sys
import argparse
import urllib

from PySide6.QtCore import *
from PySide6.QtNetwork import QNetworkCacheMetaData
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtGui import *
from PySide6.QtUiTools import QUiLoader


args = {"cacheDirectory": "", "outputDirectory": ""}

CACHE_MAGIC = 0xE8

def messageBox(text,title):
    msgBox = QMessageBox()
    msgBox.setText(text)
    msgBox.setWindowTitle(title)
    msgBox.exec()

def updateProgress(percent):
    window.progressBar.setValue(percent)

def runExtractor(cacheList):
    window.extractButton.setText("Stop")
    processed = 0
    window.progressBar.setValue(0)
    QApplication.processEvents()
    for i in cacheList:
        if window.extractButton.text() == "Extract":
            break
        extractor = CacheExtractor(i)
        if extractor.extractCache():
            extractor.saveCache()
        processed += 1
        updateProgress(processed/len(cacheList)*100)
        QApplication.processEvents()
    window.extractButton.setText("Extract")
            

class InvalidCacheMagicNumberException(Exception):
    "Raised when the cache file is invalid."

def resetOutputFolderToDefault():
    outputDirectory = os.path.abspath(os.path.join(args["cacheDirectory"],"../cacheOutput/"))
    window.outputLineEdit.setText(outputDirectory)
    args["outputDirectory"] = outputDirectory

def setCacheFolderInteractive():
    dialog = QFileDialog()
    cacheDirectory = os.path.abspath(str(dialog.getExistingDirectory(caption="Select Cache Directory")))
    window.cacheLineEdit.setText(cacheDirectory)
    args["cacheDirectory"] = cacheDirectory
    resetOutputFolderToDefault()

def setOutputFolderInteractive():
    dialog = QFileDialog()
    outputDirectory = os.path.abspath(os.path.join(dialog.getExistingDirectory(caption="Select Output Directory")))
    window.outputLineEdit.setText(outputDirectory)
    args["outputDirectory"] = outputDirectory
    
def createParser():
    parser = argparse.ArgumentParser(description="A program to extract files from a JanusVR cache.")
    parser.add_argument("directory",dest="cacheDirectory",help="JanusVR cache directory")
    parser.add_argument("-o","--output-dir",dest="outputDirectory",help="Output directory for extracted files")
    return parser.parse_args(sys.argv)

def getCacheList():
    args["cacheDirectory"] = window.cacheLineEdit.text()
    args["outputDirectory"] = window.outputLineEdit.text()
    cacheFileList = []
    cacheDirList = os.walk(args["cacheDirectory"])
    for (root,dirs,files) in cacheDirList:
        for file in files:
            if file.endswith(".d"):
                cacheFileList.append(os.path.join(root,file))
    if len(cacheFileList) == 0:
        messageBox("Cache folder does not contain cache files. (*.d)","Warning")
    return cacheFileList

def sanitizedTableIndex(index,table):
    return table[min(index,len(table)-1)]

def locationIsDir(extractor):
    for i in extractor.metadata.rawHeaders():
        if str(i[0]) == b'Location':
            print("Location: " + str(i[1]))
            return str(i[1]).endsWith("/") or str(i[1]).endsWith("\\")
    return False

class CacheExtractor():
    def __init__(self,path):
        self.path = QDir.toNativeSeparators(path)
        self.url = ""
        self.metadata = QNetworkCacheMetaData()
        self.cacheVersion = 0
        self.qtVersion = 0
        self.magicNumber = 0
        self.data = QByteArray()
        self.compressed = False
        self.fileModificationTime = QDateTime()

    def printDebug(self):
        print(f"Cache version: {self.cacheVersion}")
        print(f"URL: {self.metadata.url()}")
        print(f"Compressed: {self.compressed}")
        #print("Save to Disk: {}".format(self.metadata.saveToDisk()))
        print(f'Expiration date: {self.metadata.expirationDate().toString() or "None"}')
        print(f'Last modified: {self.metadata.lastModified().toString() or "None"}')
    def saveCache(self):
        if self.magicNumber == CACHE_MAGIC:
            endPath = self.metadata.url().path()
            cacheFolderPath = os.path.abspath(os.path.join(args["outputDirectory"],
                                           self.metadata.url().scheme(),
                                           self.metadata.url().host()))
            cacheFilePath = os.path.abspath(cacheFolderPath + urllib.parse.quote(endPath))
            if cacheFilePath.startswith(cacheFolderPath):
                cacheDir = QDir(cacheFilePath)
                if endPath == "" or locationIsDir(self) or endPath.endswith("/") or endPath.endswith("\\") or cacheFilePath == cacheFolderPath or "." not in self.metadata.url().fileName():
                    cacheDir.mkpath(".")
                    cacheFilePath = os.path.join(cacheFilePath,"index.html")
                else:
                    cacheDir = QDir(QDir.cleanPath(cacheFilePath + "/.."))
                    cacheDir.mkpath(".")
                cacheFile = QFile(QDir.toNativeSeparators(cacheFilePath))
                success = cacheFile.open(QIODevice.WriteOnly)
                if not success:
                    print(self.path)
                    print(cacheFolderPath)
                    print(cacheFilePath)
                    print(self.metadata.url().path())
                    #print(self.metadata.rawHeaders())
                cacheFile.setFileTime(self.fileModificationTime,QFileDevice.FileModificationTime)
                cacheFile.setFileTime(self.fileBirthTime,QFileDevice.FileBirthTime)
                cacheFile.write(self.data)
                cacheFile.close()
            else:
                messageBox("Cache file {self.path} path {cacheFilePath} outside folder path {cacheFolderPath}")
        else:
            print("Attempted to save invalid cache file.")
        
    def extractCache(self):
        cacheFile = QFile(self.path)
        success = cacheFile.open(QIODevice.ReadOnly)
        dataStream = QDataStream(cacheFile)
        self.fileModificationTime = cacheFile.fileTime(QFileDevice.FileModificationTime)
        self.fileBirthTime = cacheFile.fileTime(QFileDevice.FileBirthTime)
        self.magicNumber = dataStream.readInt32()
        if self.magicNumber != CACHE_MAGIC:
            print(f"{self.path} is not a valid cache file.")
            return False
        self.cacheVersion = dataStream.readInt32()
        if self.cacheVersion > 7:
            self.qtVersion = dataStream.readInt32()
        dataStream.setVersion(self.qtVersion or 13)
        dataStream >> self.metadata
        if self.metadata.lastModified().isValid():
            self.fileModificationTime = self.metadata.lastModified()
        self.compressed = dataStream.readBool()
        dataBA = QByteArray()
        if self.compressed:
            dataStream >> dataBA
            self.data = qUncompress(dataBA)
        else:
            self.data = cacheFile.readAll()
        cacheFile.close()
        #self.printDebug()
        return True

def extractEvent():
    if window.extractButton.text() == "Stop":
        window.extractButton.setText("Extract")
    else:
        cacheList = getCacheList()
        runExtractor(cacheList)

loader = QUiLoader()
app = QApplication(sys.argv)
window = loader.load("CacheSelector.ui", None)
window.show()
window.cacheButton.clicked.connect(setCacheFolderInteractive)
window.outputButton.clicked.connect(setOutputFolderInteractive)
window.extractButton.clicked.connect(extractEvent)
app.exec()
