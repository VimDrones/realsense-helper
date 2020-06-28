#!/usr/bin/env python3

import sys
sys.path.append('/usr/local/lib/')
import pyrealsense2 as rs

import cv2
import gi
import time
import numpy as np

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

frame_left = None
frame_right = None

last_process = time.time()
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, frame_type = 1,  **properties):
        super(SensorFactory, self).__init__(**properties)
        self.frame_type = frame_type
        self.number_frames = 0
        self.fps = 60
        self.duration = 1 / self.fps * Gst.SECOND
        self.launch_string = 'appsrc name=source is-live=true block=true format=GST_FORMAT_TIME ' \
                             'caps=video/x-raw,format=RGB,width=848,height=800,framerate={}/1 ' \
                             '! videoconvert ! video/x-raw,format=I420 ' \
                             '! x264enc speed-preset=ultrafast tune=zerolatency ' \
                             '! rtph264pay config-interval=1 name=pay0 pt=96'.format(self.fps)

    def on_need_data(self, src, length):
        global frame_left
        global frame_right
        frame = None
        if self.frame_type == 1:
            frame = frame_left
        elif self.frame_type == 2:
            frame = frame_right
        if frame is not None:
            data = frame.tobytes()
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)
            buf.duration = self.duration
            timestamp = self.number_frames * self.duration
            buf.pts = buf.dts = int(timestamp)
            buf.offset = timestamp
            self.number_frames += 1
            retval = src.emit('push-buffer', buf)
            last_process = time.time()
            if retval != Gst.FlowReturn.OK:
                print(retval)

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        self.number_frames = 0
        appsrc = rtsp_media.get_element().get_child_by_name('source')
        appsrc.connect('need-data', self.on_need_data)


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        for i in [1,2]:
            factory = SensorFactory(i)
            factory.set_shared(True)
            self.get_mount_points().add_factory(f"/fisheye/{i}", factory)
        self.attach(None)


Gst.init(None)

server = GstServer()

def t265_loop():
    global frame_left
    global frame_right

    print("T265 thread start...")
    pipe = rs.pipeline()
    cfg = rs.config()
    profile = pipe.start(cfg)
    print("Device connected")
    while True:
        frames = pipe.wait_for_frames()
        image_left = np.asanyarray(frames.get_fisheye_frame(1).get_data())
        image_right = np.asanyarray(frames.get_fisheye_frame(2).get_data())
        frame_left = cv2.cvtColor(image_left, cv2.COLOR_GRAY2RGB)
        frame_right = cv2.cvtColor(image_right, cv2.COLOR_GRAY2RGB)

import threading
threading.Thread(target=t265_loop, args=()).start()

loop = GLib.MainLoop()
loop.run()
