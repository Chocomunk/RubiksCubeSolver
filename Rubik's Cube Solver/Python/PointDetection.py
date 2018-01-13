import numpy as np
import cv2
import Util
from defs import *


class PointDetection:

    def __init__(self, videomanager, points_file=None, colors_file=None):
        """
        Detects all facelets on a rubik's cube using opencv for computer vision

        :param videomanager: VideoManager object that provide frames to this object for vision computations
        :param points_file: Directory of the file to store data for facelet color position. Stores data as
                            a point representing the location for which to find the color of the facelet
                            (will most likely be a point on the facelet itself)
        :param colors_file: Directory of the file to store data for the color of each of the 6 faces.
                            Each face has a list data points representing colors of that face. This list comes with
                            the following properties found from the color data points: lower_bound, upper_bound, and
                            average_color
        """
        # Input variables
        self.videomanager = videomanager
        self.points_file = points_file
        self.colors_file = colors_file

        # Facelet and color data variables
        self.facelets, self.faces = Util.generate_keys()
        self.points = Util.read_file(self.points_file)
        self.colors = Util.read_file(self.colors_file)
        self.colors_queue = []      # Queues points on the screen to be registered as a color data point for a face

        # Cube state variable, represents the colors of each facelet on the rubik's cube
        self.colors_state = dict.fromkeys(self.facelets)
        self.isCompleteCube = False

        # Detection-state variables
        self.detection_state = DetectionState.FACELETS
        self.curr_facelet_index = 0
        self.curr_face_index = 0

        # If there is no data, initialize the data files
        if not len(self.points):    # Detection state is already FACELETS
            self.clear_data()
        if not len(self.colors):    # Set detection state to COLORS, initialize, then set it back
            self.detection_state = DetectionState.COLORS
            self.clear_data()
            self.detection_state = DetectionState.FACELETS
        else:   # Set list types to numpy arrays
            Util.color_set_list_to_numpy(self.faces, self.colors)

        # Video manager mouse callback. Allows this object to control what happens during mouse presses
        self.videomanager.set_mouse_callback(self.on_mouse)

    def get_color(self, point_color):
        """
        Used to determine the face (color) of a specific facelet. Called during each draw (to draw the possible
        faces as text), and is stored in the colors_state variable every call.

        :param point_color: The rgb value of a point representing the color of a facelet
        :return: A list of possible faces (colors) that this facelet could be. The list is sorted by which face's
                 average that this color is closest to.
        """
        zscores = []
        for color, data in self.colors.items():     # loop through every face

            # if this face has at least 3 color samples, then calculate the z-score
            if data[ColorData.COLOR_SET_SIZE] and data[ColorData.COLOR_SET_SIZE] > 2:
                zscores.append((color, Util.zscore(
                    data[ColorData.COLOR_MEAN],
                    data[ColorData.COLOR_STD_DEV],
                    point_color
                )))

        # if no faces match, default to a predefined null_color value
        if not zscores:
            zscores.append((ColorData.NULL_COLOR, ColorData.NULL_COLOR_DISTANCE))

        # return the face labels sorted by their z-score magnitude
        return [e[0] for e in sorted(zscores, key=lambda x: x[1]*x[1])]

    def cycle_state_variable(self, step):
        """
        Changes the current state variable by a step

        :param step: Amount by which to change the state variable
        """
        if self.detection_state is DetectionState.FACELETS:
            self.curr_facelet_index = (self.curr_facelet_index + step) % len(self.facelets)
        if self.detection_state is DetectionState.COLORS:
            self.write_data()
            self.curr_face_index = (self.curr_face_index + step) % len(self.faces)

    def cycle_detection_state(self):
        """
        Cycles through the program's detection states\n
        Possible states:
            * COLORS
            * FACELETS
        """
        if self.detection_state is DetectionState.COLORS:
            self.write_data()
        self.detection_state = (self.detection_state + 1) % DetectionState.size

    def update(self):
        """
        Called every update of the program

        Draws onto the image frame and returns
        the frame to the video manager for display
        """
        ret, frames = self.videomanager.get_frame()

        draw_set = None
        if self.detection_state is DetectionState.FACELETS:
            draw_set = self.apply_facelet_points(ret, frames)
        if self.detection_state is DetectionState.COLORS:
            draw_set = self.apply_color_points(ret, frames)

        if draw_set:
            Util.draw_points(frames, draw_set)

        self.videomanager.set_frame(frames[0], frames[1])

    def apply_facelet_points(self, ret, frames):
        """
        Determines all facelet elements that should be drawn onto the view frames
        :param ret: Boolean list representing the status of each frame
        :param frames: List of each frame
        :return: A list of all elements to draw onto the frames
        """
        draw_set = []
        all_points_set = True
        self.isCompleteCube = True

        for facelet, point in self.points.items():  # Loop through every key and value in the dict
            if not point:   # If a point is not filled in, the virtual representation is not complete
                all_points_set = False
                self.isCompleteCube = False
                continue

            # Color current facelet point differently
            text_color = Constants.HSV_BLUE if facelet == self.facelets[self.curr_facelet_index] else Constants.HSV_GREEN
            x, y, window_num = int(point[0]), int(point[1]), point[2]-1

            if ret[window_num]:     # If this window is active
                value = self.get_color(frames[window_num][y, x])[0]
                if ColorData.NULL_COLOR in value:
                    self.isCompleteCube = False
                self.colors_state[facelet] = value

                # Add points and labels to the draw set
                draw_set.append((window_num,
                                 (" {}: {}".format(facelet, value), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.3, text_color),
                                 ((x, y), 1, text_color, 3)
                                 ))

        # Show name of current facelet
        draw_set.append((Constants.ALL_WINDOWS,
                        (self.facelets[self.curr_facelet_index], (580, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.3,
                            Constants.HSV_BLUE if all_points_set
                            else Constants.HSV_GREEN if self.points[self.facelets[self.curr_facelet_index]]
                            else Constants.HSV_RED),
                         None
                         ))
        return draw_set

    def apply_color_points(self, ret, frames):
        """
        Determines all color elements that should be drawn onto the view frames
        :param ret: Boolean list representing the status of each frame
        :param frames: List of each frame
        :return: A list of all elements to draw onto the frames
        """
        mean = self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_MEAN]
        variance = self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_VARIANCE]
        set_size = self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_SET_SIZE]
        stddev = np.zeros(3)  # To be populated later, we only care about variance here

        draw_set = []
        if len(self.colors_queue):  # If the colors queue has elements
            # Pop one point and extract data from that point
            # Note: Only one point is popped every update cycle
            point = self.colors_queue.pop(0)
            x, y, window_num, p_face = int(point[0]), int(point[1]), point[2]-1, point[3]

            if ret[window_num]:     # If this window is active
                value = frames[window_num][y, x]

                if not set_size > 0:    # No elements registered to the color set yet
                    mean = value
                    variance = np.zeros(3)
                    set_size += 1
                else:   # There are elements registered, update statistical data
                    new_mean = value/(set_size+1) + mean*set_size/(set_size+1)
                    if set_size > 1:
                        variance = (((set_size-1)*variance) + (value-mean)*(value-new_mean)) / set_size
                    else:   # Only occurs when (set_size + 1) = 2 (two elements now in set)
                        # Initialize variance calculation for 2 data points
                        variance = ((mean-new_mean) ** 2 + (value-new_mean) ** 2)
                    mean = new_mean
                    stddev = np.sqrt(variance)
                    set_size += 1

                # Set the values in the dictionary
                self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_MEAN] = mean
                self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_STD_DEV] = stddev
                self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_VARIANCE] = variance
                self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_SET_SIZE] = set_size

        # Default average color to RED (wont affect actual average, just the text color)
        if mean is None:
            mean = np.array(list(Constants.HSV_RED))

        # Add the face name to the draw set (colored to the average)
        draw_set.append((Constants.ALL_WINDOWS,
                         ("{}: {} {}".format(self.faces[self.curr_face_index], mean, stddev),
                          (40,40), cv2.FONT_HERSHEY_SIMPLEX, .5, [e.item() for e in mean]),
                         ((25,35), 3, [e.item() for e in mean], 5)
                         ))

        samples_text = ""
        text_color = Constants.HSV_RED
        if not set_size:
            samples_text = "No color samples registered"
        elif set_size < 3:
            samples_text = "Please give at least 3 samples: {}".format(set_size)
            text_color = Constants.HSV_MAGENTA
        else:
            samples_text = "Samples: {}".format(set_size)
            text_color = Constants.HSV_BLUE
        draw_set.append((Constants.ALL_WINDOWS,
                         (samples_text, (20, 65), cv2.FONT_HERSHEY_SIMPLEX, .5, text_color),
                         None))

        return draw_set

    def on_mouse(self, event, x, y, flags, window_num):
        """
        Callback for mouse events
        :param event: Received mouse event
        :param x: X position of the mouse during the event
        :param y: Y position of the mouse during the event
        :param flags: Passed flags
        :param window_num: The number of the window in which the event occupied
        """
        if self.detection_state is DetectionState.FACELETS:
            if event == cv2.EVENT_LBUTTONDOWN:
                self.points[self.facelets[self.curr_facelet_index]] = (x, y, window_num)
            if event == cv2.EVENT_RBUTTONDOWN:
                self.points[self.facelets[self.curr_facelet_index]] = None
            self.write_data()

        if self.detection_state is DetectionState.COLORS:
            if event == cv2.EVENT_LBUTTONDOWN:
                self.colors_queue.append((x, y, window_num, self.faces[self.curr_face_index]))
            if event == cv2.EVENT_RBUTTONDOWN:
                self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_MEAN] = None
                self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_STD_DEV] = None
                self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_VARIANCE] = None
                self.colors[self.faces[self.curr_face_index]][ColorData.COLOR_SET_SIZE] = 0

    def clear_data(self):
        """
        Clears all program and saved data
        """
        if self.detection_state is DetectionState.FACELETS:
            self.points = dict.fromkeys(self.facelets)
            Util.write_file(self.points_file, self.points)
        if self.detection_state is DetectionState.COLORS:
            print(self.colors)
            for face in self.faces:
                self.colors[face] = {}
                self.colors[face][ColorData.COLOR_MEAN] = None
                self.colors[face][ColorData.COLOR_STD_DEV] = None
                self.colors[face][ColorData.COLOR_VARIANCE] = None
                self.colors[face][ColorData.COLOR_SET_SIZE] = 0
            Util.write_file(self.colors_file, self.colors)

    def write_data(self):
        """
        Writes all color and facelet data to a file.
        """
        if self.detection_state is DetectionState.FACELETS:
            Util.write_file(self.points_file, self.points)
        if self.detection_state is DetectionState.COLORS:
            Util.color_set_numpy_to_list(self.faces, self.colors)
            Util.write_file(self.colors_file, self.colors)
            Util.color_set_list_to_numpy(self.faces, self.colors)
