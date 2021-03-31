import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import (
    FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure
import matplotlib.lines as lines
from matplotlib.patches import Circle, Polygon
from PyQt5 import QtGui, QtCore,QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
import numpy as np
import json as js
import os
from MyToolBar import MyToolBar, keepRatio, RulerShape
from matplotlib.path import Path
import matplotlib.patches as patches
from matplotlib.textpath import TextPath
import math
import logging
import copy

def GetGlobalPos(p2b, b2g):
    x = p2b[0] * np.cos(b2g[2]) - p2b[1] * np.sin(b2g[2])
    y = p2b[0] * np.sin(b2g[2]) + p2b[1] * np.cos(b2g[2])
    x = x + b2g[0]
    y = y + b2g[1]
    return np.array([x, y])

class Readcp (QThread):
    signal = pyqtSignal('PyQt_PyObject')
    def __init__(self):
        QThread.__init__(self)
        self.cp_name = ''
        self.js = dict()
        self.laser = []
    # run method gets called when we start the thread
    def run(self):
        fid = open(self.cp_name, encoding= 'UTF-8')
        self.js = js.load(fid)
        fid.close()
        self.laser = dict()
        x, y, r = 0, 0, 0
        if 'deviceTypes' in self.js:
            for device in self.js['deviceTypes']:
                if device['name'] == 'laser':
                    for laser in device['devices']:
                        for param in laser['deviceParams']:
                            if param['key'] == 'basic':
                                for p in param['arrayParam']['params']:
                                    if p['key'] == 'x':
                                        x = p['doubleValue']
                                    elif p['key'] == 'y':
                                        y = p['doubleValue']
                                    elif p['key'] == 'yaw':
                                        r = p['doubleValue']
                        self.laser[laser['name']] = [float(x), float(y), np.deg2rad(r)]
                    break
        self.signal.emit(self.cp_name)

class Readmodel(QThread):
    signal = pyqtSignal('PyQt_PyObject')
    def __init__(self):
        QThread.__init__(self)
        self.model_name = ''
        self.js = dict()
        self.head = None
        self.tail = None 
        self.width = None
        self.loc_laser_ind = 0
        self.laser = dict() #x,y,r
        self.laser_id2name = dict()
    # run method gets called when we start the thread
    def run(self):
        with open(self.model_name, 'r',encoding= 'UTF-8') as fid:
            try:
                self.js = js.load(fid)
            except:
                logging.error("robot model file cannot read!!!")
            # fid.close()
            self.head = None
            self.tail = None 
            self.width = None
            self.laser = dict() #x,y,r
            if 'chassis' in self.js:
                self.head = float(self.js['chassis']['head'])
                self.tail = float(self.js['chassis']['tail'])
                self.width = float(self.js['chassis']['width'])
                laser0 = self.js['laser']['index'][0]
                self.laser[0] = [float(laser0['x']),float(laser0['y']),np.deg2rad(float(laser0['r']))]
            elif 'deviceTypes' in self.js:
                for device in self.js['deviceTypes']:
                    if device['name'] == 'chassis':
                        for param in device['devices'][0]['deviceParams']:
                            if param['key'] == 'shape':
                                for childparam in param['comboParam']['childParams']:
                                    if childparam['key'] == 'rectangle':
                                        if param['comboParam']['childKey'] == childparam['key']:
                                            for p in childparam['params']:
                                                if p['key'] == 'width':
                                                    self.width = p['doubleValue']
                                                elif p['key'] == 'head':
                                                    self.head = p['doubleValue']
                                                elif p['key'] == 'tail':
                                                    self.tail = p['doubleValue']
                                    elif childparam['key'] == 'circle':
                                        if param['comboParam']['childKey'] == childparam['key']:
                                            for p in childparam['params']:
                                                if p['key'] == 'radius':
                                                    self.width = p['doubleValue']
                                                    self.head = self.width
                                                    self.tail = self.width
                    elif device['name'] == 'laser':
                        x, y, r, idx = 0, 0, 0, 0
                        for laser in device['devices']:
                            for param in laser['deviceParams']:
                                if param['key'] == 'basic':
                                    for p in param['arrayParam']['params']:
                                        if p['key'] == 'x':
                                            x = p['doubleValue']
                                        elif p['key'] == 'y':
                                            y = p['doubleValue']
                                        elif p['key'] == 'yaw':
                                            r = p['doubleValue']
                                        elif p['key'] == 'id':
                                            idx = p['uint32Value']
                                        elif p['key'] == 'useForLocalization':
                                            if p['boolValue'] == True:
                                                self.loc_laser_ind = idx
                            self.laser[idx] = [float(x),float(y),np.deg2rad(r)]
                            self.laser_id2name[idx] = laser['name']
            else:
                logging.error('Cannot Open robot.model: ' + self.model_name)
            self.signal.emit(self.model_name)

class Readmap(QThread):
    signal = pyqtSignal('PyQt_PyObject')
    def __init__(self):
        QThread.__init__(self)
        self.map_name = ''
        self.js = dict()
        self.map_x = []
        self.map_y = []
        self.verts = []
        self.circles = []
        self.points = []
        self.straights = []
        self.bezier_codes = [ 
            Path.MOVETO,
            Path.CURVE4,
            Path.CURVE4,
            Path.CURVE4,
            ]
        self.straight_codes = [
            Path.MOVETO,
            Path.LINETO ,
        ]
    # run method gets called when we start the thread
    def run(self):
        fid = open(self.map_name, encoding= 'UTF-8')
        self.js = js.load(fid)
        fid.close()
        self.map_x = []
        self.map_y = []
        self.verts = []
        self.circles = []
        self.straights = []
        self.points = []
        self.p_names = []
        # print(self.js.keys())
        for pos in self.js['normalPosList']:
            if 'x' in pos:
                self.map_x.append(float(pos['x']))
            else:
                self.map_x.append(0.0)
            if 'y' in pos:
                self.map_y.append(float(pos['y']))
            else:
                self.map_y.append(0.0)
        if 'advancedCurveList' in self.js:
            for line in self.js['advancedCurveList']:
                if line['className'] == 'BezierPath':
                    x0 = 0
                    y0 = 0
                    x1 = 0
                    y1 = 0
                    x2 = 0
                    y2 = 0
                    x3 = 0
                    y3 = 0
                    if 'x' in line['startPos']['pos']:
                        x0 = line['startPos']['pos']['x']
                    if 'y' in line['startPos']['pos']:
                        y0 = line['startPos']['pos']['y']
                    if 'x' in line['controlPos1']:
                        x1 = line['controlPos1']['x']
                    if 'y' in line['controlPos1']:
                        y1 = line['controlPos1']['y']
                    if 'x' in line['controlPos2']:
                        x2 = line['controlPos2']['x']
                    if 'y' in line['controlPos2']:
                        y2 = line['controlPos2']['y']
                    if 'x' in line['endPos']['pos']:
                        x3 = line['endPos']['pos']['x']
                    if 'y' in line['endPos']['pos']:
                        y3 = line['endPos']['pos']['y']
                    self.verts.append([(x0,y0),(x1,y1),(x2,y2),(x3,y3)])
                elif line['className'] == 'ArcPath':
                    x1 = 0
                    y1 = 0
                    x2 = 0
                    y2 = 0
                    x3 = 0
                    y3 = 0
                    if 'x' in line['startPos']['pos']:
                        x1 = line['startPos']['pos']['x']
                    if 'y' in line['startPos']['pos']:
                        y1 = line['startPos']['pos']['y']
                    if 'x' in line['controlPos1']:
                        x2 = line['controlPos1']['x']
                    if 'y' in line['controlPos1']:
                        y2 = line['controlPos1']['y']
                    if 'x' in line['endPos']['pos']:
                        x3 = line['endPos']['pos']['x']
                    if 'y' in line['endPos']['pos']:
                        y3 = line['endPos']['pos']['y']
                    A = x1*(y2-y3) - y1*(x2-x3)+x2*y3-x3*y2
                    B = (x1*x1 + y1*y1)*(y3-y2)+(x2*x2+y2*y2)*(y1-y3)+(x3*x3+y3*y3)*(y2-y1)
                    C = (x1*x1 + y1*y1)*(x2-x3)+(x2*x2+y2*y2)*(x3-x1)+(x3*x3+y3*y3)*(x1-x2)
                    D = (x1*x1 + y1*y1)*(x3*y2-x2*y3)+(x2*x2+y2*y2)*(x1*y3-x3*y1)+(x3*x3+y3*y3)*(x2*y1-x1*y2)
                    if abs(A) > 1e-12:
                        x = -B/2/A
                        y = -C/2/A
                        r = math.sqrt((B*B+C*C-4*A*D)/(4*A*A))
                        theta1 = math.atan2(y1-y,x1-x)
                        theta3 = math.atan2(y3-y,x3-x)
                        v1 = np.array([x2-x1,y2-y1])
                        v2 = np.array([x3-x2,y3-y2])
                        flag = float(np.cross(v1,v2))
                        if flag >= 0:
                            self.circles.append([x, y, r, np.rad2deg(theta1), np.rad2deg(theta3)])
                        else:
                            self.circles.append([x, y, r, np.rad2deg(theta3), np.rad2deg(theta1)])
                    else:
                        self.straights.append([(x1,y1),(x3,y3)])
                elif line['className'] == 'StraightPath':
                    x1 = 0
                    y1 = 0
                    x2 = 0
                    y2 = 0
                    if 'x' in line['startPos']['pos']:
                        x1 = line['startPos']['pos']['x']
                    if 'y' in line['startPos']['pos']:
                        y1 = line['startPos']['pos']['y']
                    if 'x' in line['endPos']['pos']:
                        x2 = line['endPos']['pos']['x']
                    if 'y' in line['endPos']['pos']:
                        y2 = line['endPos']['pos']['y']
                    self.straights.append([(x1,y1),(x2,y2)])
        if 'advancedPointList' in self.js:
            for pt in self.js['advancedPointList']:
                x0 = 0
                y0 = 0 
                theta = 0
                if 'x' in pt['pos']:
                    x0 = pt['pos']['x']
                if 'y' in pt['pos']:
                    y0 = pt['pos']['y']
                if 'dir' in pt:
                    theta = pt['dir']
                if  'ignoreDir' in pt:
                    if pt['ignoreDir'] == True:
                        theta = None
                self.points.append([x0,y0,theta])
                self.p_names.append([pt['instanceName']])
        self.signal.emit(self.map_name)


class MapWidget(QtWidgets.QWidget):
    dropped = pyqtSignal('PyQt_PyObject')
    hiddened = pyqtSignal('PyQt_PyObject')
    def __init__(self):
        super(QtWidgets.QWidget, self).__init__()
        self.setWindowTitle('MapViewer')
        self.map_name = None
        self.model_name = None
        self.cp_name = None
        self.draw_size = [] #xmin xmax ymin ymax
        self.map_data = lines.Line2D([],[], marker = '.', linestyle = '', markersize = 1.0)
        self.laser_data = lines.Line2D([],[], marker = 'o', markersize = 2.0, 
                                        linestyle = '-', linewidth = 0.1, 
                                        color='r', alpha = 0.5)
        self.robot_data = lines.Line2D([],[], linestyle = '-', color='k')
        self.robot_data_c0 = lines.Line2D([],[], linestyle = '-', linewidth = 2, color='k')
        self.robot_loc_data = lines.Line2D([],[], linestyle = '--', color='gray')
        self.robot_loc_data_c0 = lines.Line2D([],[], linestyle = '--', linewidth = 2, color='gray')
        self.obs_points = lines.Line2D([],[], linestyle = '', marker = '*', markersize = 8.0, color='k')
        self.depthCamera_hole_points = lines.Line2D([],[], linestyle = '', marker = 'o', markersize = 4.0, color='black')
        self.depthCamera_obs_points = lines.Line2D([],[], linestyle = '', marker = 'o', markersize = 4.0, color='gray')
        self.particle_points = lines.Line2D([],[], linestyle = '', marker = 'o', markersize = 4.0, color='b')
        self.particle_points.set_zorder(101)
        self.trajectory = lines.Line2D([],[], linestyle = '', marker = 'o', markersize = 2.0, color='m')
        self.trajectory_next = lines.Line2D([],[], linestyle = '', marker = 'o', markersize = 2.0, color='mediumpurple')
        self.cur_arrow = patches.FancyArrow(0, 0, 0.5, 0,
                                            length_includes_head=True,# 增加的长度包含箭头部分
                                            width=0.05,
                                            head_width=0.1, head_length=0.16, fc='r', ec='b')
        self.cur_arrow.set_zorder(100)
        self.org_arrow_xy = self.cur_arrow.get_xy().copy()

        self.robot_pos = []
        self.robot_loc_pos = []
        self.laser_pos = dict()
        self.laser_org_data = np.array([])
        self.laser_index = -1
        self.check_draw_flag = False
        self.fig_ratio = 1.0
        self.setAcceptDrops(True)
        self.dropped.connect(self.dragFiles)
        self.read_map = Readmap()
        self.read_map.signal.connect(self.readMapFinished)
        self.read_model = Readmodel()
        self.read_model.signal.connect(self.readModelFinished)
        self.read_cp = Readcp()
        self.read_cp.signal.connect(self.readCPFinished)
        self.setupUI()

    def setupUI(self):
        self.static_canvas = FigureCanvas(Figure(figsize=(5,5)))
        self.static_canvas.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        self.static_canvas.figure.subplots_adjust(left = 0.0, right = 1.0, bottom = 0.0, top = 1.0)
        self.static_canvas.figure.tight_layout()
        self.ax= self.static_canvas.figure.subplots(1, 1)
        self.ax.add_line(self.map_data)
        self.ax.add_patch(self.cur_arrow)
        self.ax.add_line(self.robot_data)
        self.ax.add_line(self.robot_data_c0)
        self.ax.add_line(self.robot_loc_data)
        self.ax.add_line(self.robot_loc_data_c0)
        self.ax.add_line(self.laser_data)
        self.ax.add_line(self.obs_points)
        self.ax.add_line(self.depthCamera_hole_points)
        self.ax.add_line(self.depthCamera_obs_points)
        self.ax.add_line(self.particle_points)
        self.ax.add_line(self.trajectory)
        self.ax.add_line(self.trajectory_next)
        self.ruler = RulerShape()
        self.ruler.add_ruler(self.ax)
        MyToolBar.home = self.toolbarHome
        self.toolbar = MyToolBar(self.static_canvas, self, ruler = self.ruler)
        self.toolbar.fig_ratio = 1
        self.fig_layout = QtWidgets.QVBoxLayout(self)
        self.file_lable = QtWidgets.QLabel(self)
        self.file_lable.setText('1. 将地图(*.smap)文件拖入窗口')
        self.file_lable.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.file_lable.setFixedHeight(16.0)
        self.robot_lable = QtWidgets.QLabel(self)
        self.robot_lable.setText('2. 机器人模型(*.model)文件拖入窗口')
        self.robot_lable.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.robot_lable.setFixedHeight(16.0)
        self.cp_lable = QtWidgets.QLabel(self)
        self.cp_lable.setText('3. (可选)机器人标定(*.cp)文件拖入窗口')
        self.cp_lable.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.cp_lable.setFixedHeight(16.0)
        self.timestamp_lable = QtWidgets.QLabel(self)
        self.timestamp_lable.setText('实框定位: ')
        self.timestamp_lable.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.timestamp_lable.setFixedHeight(16.0)
        self.logt_lable = QtWidgets.QLabel(self)
        self.logt_lable.setText('虚框定位: ')
        self.logt_lable.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.logt_lable.setFixedHeight(16.0)
        self.obs_lable = QtWidgets.QLabel(self)
        self.obs_lable.setText('')
        self.obs_lable.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.obs_lable.setFixedHeight(16.0)
        self.fig_layout.addWidget(self.toolbar)
        self.fig_layout.addWidget(self.file_lable)
        self.fig_layout.addWidget(self.robot_lable)
        self.fig_layout.addWidget(self.cp_lable)
        self.fig_layout.addWidget(self.timestamp_lable)
        self.fig_layout.addWidget(self.logt_lable)
        self.fig_layout.addWidget(self.obs_lable)
        self.fig_layout.addWidget(self.static_canvas)
        self.static_canvas.mpl_connect('resize_event', self.resize_fig)

                #选择消息框
        self.hbox = QtWidgets.QHBoxLayout()
        self.check_all = QtWidgets.QCheckBox('ALL',self)
        self.check_all.setFocusPolicy(QtCore.Qt.NoFocus)
        self.check_map = QtWidgets.QCheckBox('MAP',self)
        self.check_map.setFocusPolicy(QtCore.Qt.NoFocus)
        self.check_robot = QtWidgets.QCheckBox('ROBOT',self)
        self.check_robot.setFocusPolicy(QtCore.Qt.NoFocus)
        self.check_partical = QtWidgets.QCheckBox('Paritical',self)
        self.check_partical.setFocusPolicy(QtCore.Qt.NoFocus)
        self.hbox.addWidget(self.check_all)
        self.hbox.addWidget(self.check_map)
        self.hbox.addWidget(self.check_robot)
        self.hbox.addWidget(self.check_partical)
        self.check_all.stateChanged.connect(self.changeCheckBoxAll)
        self.check_map.stateChanged.connect(self.changeCheckBox)
        self.check_robot.stateChanged.connect(self.changeCheckBox)
        self.check_partical.stateChanged.connect(self.changeCheckBox)

        self.check_lasers = dict()
        self.hbox.setAlignment(QtCore.Qt.AlignLeft)
        self.fig_layout.addLayout(self.hbox)
        self.check_all.setChecked(True)
        
    def add_laser_check(self, index):
        self.check_lasers[index] = QtWidgets.QCheckBox('Laser'+str(index),self)
        self.check_lasers[index].setFocusPolicy(QtCore.Qt.NoFocus)
        self.check_lasers[index].stateChanged.connect(self.changeCheckBox)
        self.hbox.addWidget(self.check_lasers[index])

    def changeCheckBoxAll(self):
        if self.check_all.checkState() == QtCore.Qt.Checked:
            self.check_map.setChecked(True)
            self.check_robot.setChecked(True)
            self.check_partical.setChecked(True)
            for k in self.check_lasers.keys():
                self.check_lasers[k].setChecked(True)
        elif self.check_all.checkState() == QtCore.Qt.Unchecked:
            self.check_map.setChecked(False)
            self.check_robot.setChecked(False)
            self.check_partical.setChecked(False)
            for k in self.check_lasers.keys():
                self.check_lasers[k].setChecked(False)

    def changeCheckBox(self):
        all_laser_check = True
        part_laser_check = False
        for k in self.check_lasers.keys():
            if self.check_lasers[k].isChecked:
                part_laser_check = True
            else:
                all_laser_check = False
        if self.check_map.isChecked() and self.check_robot.isChecked() and all_laser_check\
            and self.check_partical.isChecked():
            self.check_all.setCheckState(QtCore.Qt.Checked)
        elif self.check_map.isChecked() or self.check_robot.isChecked() or part_laser_check\
            or self.check_partical.isChecked():
            self.check_all.setTristate()
            self.check_all.setCheckState(QtCore.Qt.PartiallyChecked)
        else:
            self.check_all.setTristate(False)
            self.check_all.setCheckState(QtCore.Qt.Unchecked)

        cur_check = self.sender()
        if cur_check is self.check_robot:
            self.robot_data.set_visible(cur_check.isChecked())
            self.cur_arrow.set_visible(cur_check.isChecked())
            self.cur_arrow.set_visible(cur_check.isChecked())
        elif cur_check is self.check_map:
            self.map_data.set_visible(cur_check.isChecked())
        elif cur_check is self.check_partical:
            self.particle_points.set_visible(cur_check.isChecked())
        else:
            for k in self.check_lasers.keys():
                if cur_check is self.check_lasers[k]:
                    if self.laser_index is k:
                        self.laser_data.set_visible(cur_check.isChecked())
                       
        self.static_canvas.figure.canvas.draw() 

    def closeEvent(self,event):
        self.hide()
        self.hiddened.emit(True)

    def toolbarHome(self, *args, **kwargs):
        if len(self.draw_size) == 4:
            xmin, xmax, ymin ,ymax = keepRatio(self.draw_size[0], self.draw_size[1], self.draw_size[2], self.draw_size[3], self.fig_ratio)
            self.ax.set_xlim(xmin,xmax)
            self.ax.set_ylim(ymin,ymax)
            self.static_canvas.figure.canvas.draw()

    def resize_fig(self, event):
        ratio = event.width/event.height
        self.fig_ratio = ratio
        self.toolbar.fig_ratio = ratio
        (xmin, xmax) = self.ax.get_xlim()
        (ymin, ymax) = self.ax.get_ylim()
        bigger = True
        if len(self.draw_size) == 4:
            factor = 1.5
            if not(xmin > self.draw_size[0]*factor or xmax < self.draw_size[1]*factor or ymin > self.draw_size[2]*factor or ymax < self.draw_size[3]*factor):
                bigger = False
        xmin, xmax, ymin ,ymax = keepRatio(xmin, xmax, ymin, ymax, ratio, bigger)
        self.ax.set_xlim(xmin,xmax)
        self.ax.set_ylim(ymin,ymax)
        self.static_canvas.figure.canvas.draw()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
            links = []
            for url in event.mimeData().urls():
                links.append(str(url.toLocalFile()))
            self.dropped.emit(links)
        else:
            event.ignore()

    def dragFiles(self,files):
        new_map = False
        new_model = False
        new_cp = False
        for file in files:
            if file and os.path.exists(file):
                if os.path.splitext(file)[1] == ".smap":
                    self.map_name = file
                    new_map = True
                elif os.path.splitext(file)[1] == ".model":
                    self.model_name = file
                    new_model = True
                elif os.path.splitext(file)[1] == ".cp":
                    self.cp_name = file
                    new_cp = True
        if new_map and self.map_name:
            self.read_map.map_name = self.map_name
            self.file_lable.hide()
            self.read_map.start()
        if new_model and self.model_name:
            self.read_model.model_name = self.model_name
            self.robot_lable.hide()
            self.read_model.start()
        if new_cp and self.cp_name:
            self.read_cp.cp_name = self.cp_name
            self.cp_lable.hide()
            self.read_cp.start()


    def readMapFinished(self, result):
        if len(self.read_map.map_x) > 0:
            self.map_data.set_xdata(self.read_map.map_x)
            self.map_data.set_ydata(self.read_map.map_y)
            self.ax.grid()
            self.ax.axis('auto')
            xmin = min(self.read_map.map_x)
            xmax = max(self.read_map.map_x)
            ymin = min(self.read_map.map_y)
            ymax = max(self.read_map.map_y)
            if xmax - xmin > ymax - ymin:
                ymax = ymin + xmax - xmin
            else:
                xmax = xmin + ymax - ymin
            self.draw_size = [xmin, xmax, ymin ,ymax]
            self.ax.set_xlim(xmin, xmax)
            self.ax.set_ylim(ymin, ymax)
            [p.remove() for p in reversed(self.ax.patches)]
            [p.remove() for p in reversed(self.ax.texts)]
            self.ax.add_patch(self.cur_arrow) #add robot arrow again
            for vert in self.read_map.verts:
                path = Path(vert, self.read_map.bezier_codes)
                patch = patches.PathPatch(path, facecolor='none', edgecolor='orange', lw=1)
                self.ax.add_patch(patch)
            for circle in self.read_map.circles:
                wedge = patches.Arc([circle[0], circle[1]], circle[2]*2, circle[2]*2, 0, circle[3], circle[4], facecolor = 'none', ec="orange", lw = 1)
                self.ax.add_patch(wedge)
            for vert in self.read_map.straights:
                path = Path(vert, self.read_map.straight_codes)
                patch = patches.PathPatch(path, facecolor='none', edgecolor='orange', lw=2)
                self.ax.add_patch(patch)
            pr = 0.25
            for (pt,name) in zip(self.read_map.points, self.read_map.p_names):
                circle = patches.Circle((pt[0], pt[1]), pr, facecolor='orange',
                edgecolor=(0, 0.8, 0.8), linewidth=3, alpha=0.5)
                self.ax.add_patch(circle)
                text_path = TextPath((pt[0],pt[1]), name[0], size = 0.2)
                text_path = patches.PathPatch(text_path, ec="none", lw=3, fc="k")
                self.ax.add_patch(text_path)
                if pt[2] != None:
                    arrow = patches.Arrow(pt[0],pt[1], pr * np.cos(pt[2]), pr*np.sin(pt[2]), pr)
                    self.ax.add_patch(arrow)

            self.static_canvas.figure.canvas.draw()

    def readModelFinished(self, result):
        if self.read_model.head and self.read_model.tail and self.read_model.width:
            if self.laser_index is -1:
                if len(self.read_model.laser) > 0:
                    self.laser_index = list(self.read_model.laser.keys())[0]
            if self.laser_index in self.read_model.laser.keys():
                for i in range(0, self.hbox.count()): 
                    self.hbox.itemAt(i).widget().deleteLater()
                self.check_all = QtWidgets.QCheckBox('ALL',self)
                self.check_all.setFocusPolicy(QtCore.Qt.NoFocus)
                self.check_map = QtWidgets.QCheckBox('MAP',self)
                self.check_map.setFocusPolicy(QtCore.Qt.NoFocus)
                self.check_robot = QtWidgets.QCheckBox('ROBOT',self)
                self.check_robot.setFocusPolicy(QtCore.Qt.NoFocus)
                self.check_partical = QtWidgets.QCheckBox('Paritical',self)
                self.check_partical.setFocusPolicy(QtCore.Qt.NoFocus)
                self.hbox.addWidget(self.check_all)
                self.hbox.addWidget(self.check_map)
                self.hbox.addWidget(self.check_robot)
                self.hbox.addWidget(self.check_partical)
                self.check_all.stateChanged.connect(self.changeCheckBoxAll)
                self.check_map.stateChanged.connect(self.changeCheckBox)
                self.check_robot.stateChanged.connect(self.changeCheckBox)
                self.check_partical.stateChanged.connect(self.changeCheckBox)
                for k in self.read_model.laser.keys():
                    self.add_laser_check(k)
                self.check_all.setChecked(True)

                xdata = [-self.read_model.tail, -self.read_model.tail, self.read_model.head, self.read_model.head, -self.read_model.tail]
                ydata = [self.read_model.width/2, -self.read_model.width/2, -self.read_model.width/2, self.read_model.width/2, self.read_model.width/2]
                robot_shape = np.array([xdata, ydata])
                xxdata = [-0.05, 0.05, 0.0, 0.0, 0.0]
                xydata = [0.0, 0.0, 0.0, 0.05, -0.05]
                cross_shape = np.array([xxdata,xydata])
                self.laser_pos = copy.deepcopy(self.read_model.laser)
                laser_data = [self.laser_pos[self.laser_index][0], self.laser_pos[self.laser_index][1]]
                if not self.robot_pos:
                    if len(self.draw_size) == 4:
                        xmid = (self.draw_size[0] + self.draw_size[1])/2
                        ymid = (self.draw_size[2] + self.draw_size[3])/2
                    else:
                        xmid = 0.5
                        ymid = 0.5
                    self.robot_pos = [xmid, ymid, 0.0]
                    self.robot_loc_pos = [xmid, ymid, 0.0]
                robot_shape = GetGlobalPos(robot_shape,self.robot_pos)
                self.robot_data.set_xdata(robot_shape[0])
                self.robot_data.set_ydata(robot_shape[1])
                cross_shape = GetGlobalPos(cross_shape,self.robot_pos)
                self.robot_data_c0.set_xdata(cross_shape[0])
                self.robot_data_c0.set_ydata(cross_shape[1])
                if self.laser_org_data.any():
                    laser_data = GetGlobalPos(self.laser_org_data, self.laser_pos[self.laser_index])
                laser_data = GetGlobalPos(laser_data, self.robot_pos)
                self.laser_data.set_xdata(laser_data[0])
                self.laser_data.set_ydata(laser_data[1])

                cross_shape = np.array([xxdata,xydata])
                cross_shape = GetGlobalPos(cross_shape,self.robot_pos)
                self.robot_loc_data_c0.set_xdata(cross_shape[0])
                self.robot_loc_data_c0.set_ydata(cross_shape[1])
                robot_shape = np.array([xdata, ydata])
                robot_shape = GetGlobalPos(robot_shape,self.robot_loc_pos)
                self.robot_loc_data_c0.set_xdata([self.robot_pos[0]])
                self.robot_loc_data_c0.set_ydata([self.robot_pos[1]])

                if len(self.draw_size) != 4:
                    xmax = self.robot_pos[0] + 10
                    xmin = self.robot_pos[0] - 10
                    ymax = self.robot_pos[1] + 10
                    ymin = self.robot_pos[1] - 10
                    self.draw_size = [xmin,xmax, ymin, ymax]
                    self.ax.set_xlim(xmin, xmax)
                    self.ax.set_ylim(ymin, ymax)
                self.static_canvas.figure.canvas.draw()
            else:
                print("read laser error! laser_index: ", self.laser_index, "; laser index in model: ", self.read_model.laser.keys())
                logging.debug("read laser error! laser_index: " + str(self.laser_index) +" "+ str(self.read_model.laser.keys()))
        else:
            print("readModel error!")
            logging.debug("readModel error!")
    

    

    def readCPFinished(self, result):
        if self.read_model.laser:
            if self.read_cp.laser:
                for key in self.read_model.laser.keys():
                    self.laser_pos[key] = [0,0,0]
                    laser_name = self.read_model.laser_id2name[key]
                    if laser_name in self.read_cp.laser.keys():
                        self.laser_pos[key][0] = self.read_model.laser[key][0] + self.read_cp.laser[laser_name][0]
                        self.laser_pos[key][1] = self.read_model.laser[key][1] + self.read_cp.laser[laser_name][1]
                        self.laser_pos[key][2] = self.read_model.laser[key][2] + self.read_cp.laser[laser_name][2]
                    else:
                        self.laser_pos[key][0] = self.read_model.laser[key][0]
                        self.laser_pos[key][1] = self.read_model.laser[key][1]
                        self.laser_pos[key][2] = self.read_model.laser[key][2]
                    laser_data = [self.laser_pos[key][0], self.laser_pos[key][1]]
                    if self.laser_org_data.any() and self.laser_index == key:
                        laser_data = GetGlobalPos(self.laser_org_data, self.laser_pos[self.laser_index])
                        laser_data = GetGlobalPos(laser_data, self.robot_pos)
                        self.laser_data.set_xdata(laser_data[0])
                        self.laser_data.set_ydata(laser_data[1])
                        self.static_canvas.figure.canvas.draw()

    def readtrajectory(self, x, y, xn, yn, x0, y0, r0):
        self.trajectory.set_xdata(x)
        self.trajectory.set_ydata(y)
        self.trajectory_next.set_xdata(xn)
        self.trajectory_next.set_ydata(yn)
        data = self.org_arrow_xy.copy()
        tmp_data = data.copy()
        data[:,0]= tmp_data[:,0] * np.cos(r0) - tmp_data[:,1] * np.sin(r0)
        data[:,1] = tmp_data[:,0] * np.sin(r0) + tmp_data[:,1] * np.cos(r0)
        data = data + [x0, y0]
        self.cur_arrow.set_xy(data)
        if len(self.draw_size) != 4:
                xmax = max(x) + 10 
                xmin = min(x) - 10
                ymax = max(y) + 10
                ymin = min(y) - 10
                self.draw_size = [xmin,xmax, ymin, ymax]
                self.ax.set_xlim(xmin, xmax)
                self.ax.set_ylim(ymin, ymax)

    def updateRobotLaser(self, laser_org_data, laser_index, robot_pos, robot_loc_pos, laser_info, loc_info, obs_pos, obs_info, depthcamera_pos, particle_pos):
        self.timestamp_lable.setText('实框定位: '+ laser_info)
        self.logt_lable.setText('虚框定位: '+ loc_info)
        if obs_info != '':
            self.obs_lable.setText('障碍物信息: ' + obs_info)
            self.obs_lable.show()
        else:
            self.obs_lable.setText('')
        self.robot_pos = robot_pos
        self.robot_loc_pos = robot_loc_pos
        self.laser_org_data = laser_org_data
        self.laser_index = laser_index
        if obs_pos:
            self.obs_points.set_xdata([obs_pos[0]])
            self.obs_points.set_ydata([obs_pos[1]])
        else:
            self.obs_points.set_xdata([])
            self.obs_points.set_ydata([])
        if len(depthcamera_pos) > 0:
            hole_points = [[],[]]
            obs_points = [[],[]]
            for ind, val in enumerate(depthcamera_pos[2]):
                if val < 0:
                    hole_points[0].append(depthcamera_pos[0][ind])
                    hole_points[1].append(depthcamera_pos[1][ind])
                else:
                    obs_points[0].append(depthcamera_pos[0][ind])
                    obs_points[1].append(depthcamera_pos[1][ind])
            self.depthCamera_hole_points.set_xdata([hole_points[0]])
            self.depthCamera_hole_points.set_ydata([hole_points[1]])
            self.depthCamera_obs_points.set_xdata([obs_points[0]])
            self.depthCamera_obs_points.set_ydata([obs_points[1]])
        else:
            self.depthCamera_hole_points.set_xdata([])
            self.depthCamera_hole_points.set_ydata([])
            self.depthCamera_obs_points.set_xdata([])
            self.depthCamera_obs_points.set_ydata([])
        if len(particle_pos) > 0:
            points = [[],[]]
            for ind, val in enumerate(particle_pos[2]):
                points[0].append(particle_pos[0][ind])
                points[1].append(particle_pos[1][ind])
            self.particle_points.set_xdata([points[0]])
            self.particle_points.set_ydata([points[1]])
        else:
            self.particle_points.set_xdata([])
            self.particle_points.set_ydata([])

        if self.laser_index in self.laser_pos.keys() \
         and self.read_model.tail and self.read_model.head and self.read_model.width:
            xdata = [-self.read_model.tail, -self.read_model.tail, self.read_model.head, self.read_model.head, -self.read_model.tail]
            ydata = [self.read_model.width/2, -self.read_model.width/2, -self.read_model.width/2, self.read_model.width/2, self.read_model.width/2]
            robot_shape = np.array([xdata, ydata])
            xxdata = [-0.05, 0.05, 0.0, 0.0, 0.0]
            xydata = [0.0, 0.0, 0.0, 0.05, -0.05]
            cross_shape = np.array([xxdata,xydata])
            robot_shape = GetGlobalPos(robot_shape,robot_pos)
            self.robot_data.set_xdata(robot_shape[0])
            self.robot_data.set_ydata(robot_shape[1])
            cross_shape = GetGlobalPos(cross_shape,self.robot_pos)
            self.robot_data_c0.set_xdata(cross_shape[0])
            self.robot_data_c0.set_ydata(cross_shape[1])
            if self.laser_index in self.check_lasers:
                self.laser_data.set_visible(self.check_lasers[self.laser_index].isChecked())
            laser_data = GetGlobalPos(laser_org_data, self.laser_pos[self.laser_index])
            laser_data = GetGlobalPos(laser_data,robot_pos)
            self.laser_data.set_xdata(laser_data[0])
            self.laser_data.set_ydata(laser_data[1])

            cross_shape = np.array([xxdata,xydata])
            cross_shape = GetGlobalPos(cross_shape,robot_loc_pos)
            self.robot_loc_data_c0.set_xdata(cross_shape[0])
            self.robot_loc_data_c0.set_ydata(cross_shape[1])
            robot_shape = np.array([xdata, ydata])
            robot_shape = GetGlobalPos(robot_shape,robot_loc_pos)
            self.robot_loc_data.set_xdata(robot_shape[0])
            self.robot_loc_data.set_ydata(robot_shape[1])
    def redraw(self):
        self.static_canvas.figure.canvas.draw()


if __name__ == '__main__':
    import sys
    import os
    app = QtWidgets.QApplication(sys.argv)
    form = MapWidget()
    form.show()
    app.exec_()
