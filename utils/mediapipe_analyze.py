import cv2
import mediapipe as mp
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm import tqdm
import os
import warnings

# Ignore warnings
warnings.filterwarnings('ignore')

# OPTION to display video with hand tracking
DISPLAY = False

# Create mediapipe solutions for hand tracking
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

# Get list of video files from the directory 'videos-raw'
files = os.listdir('videos-raw')

# Loop through each video file in the directory
for file in files:
    VIDEO_FILE = file.replace('.mp4','')

    # Initialize Mediapipe Hands object with desired parameters
    hands = mp_hands.Hands(
        static_image_mode = False,
        max_num_hands = 1,
        model_complexity = 1,
        min_detection_confidence = 0.8, 
        min_tracking_confidence  = 0.8
    )

    # Open the video file
    cap = cv2.VideoCapture('videos-raw/'+VIDEO_FILE+'.mp4')
    video_length = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width  = cap.get(cv2.CAP_PROP_FRAME_WIDTH)   # float `width`
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)  # float `height`

    # Print the absolute path of the video file
    print(os.path.abspath('videos-raw/'+VIDEO_FILE+'.mp4'))

    # Initialize array to store hand landmark data
    data = np.zeros((video_length, 63))
    first = True

    # Check if video file opened successfully
    if not cap.isOpened():
        print('Error:'+VIDEO_FILE+' not loaded.')
    else:
        # Process each frame of the video
        for i in tqdm(range(video_length)):
            success, image = cap.read()
            if not success:
                print("Error or video finished.")
                break

            # Improve performance by marking the image as not writeable
            image.flags.writeable = False
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = hands.process(image)

            # Initialize array to store hand landmark positions
            arr = np.zeros(63)
            j = 0

            # If hand landmarks are detected, process them
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    for id, landmark in enumerate(hand_landmarks.landmark):
                        arr[j]   = landmark.x * width
                        arr[j+1] = landmark.y * height
                        arr[j+2] = results.multi_handedness[0].classification[0].score
                        j = j+3
                        #print(f'Landmark {id}: (X: {landmark.x}, Y: {landmark.y}, Z: {landmark.z})')
            else:
                # If no hand landmarks detected, set positions and score to zero
                arr[j]   = 0
                arr[j+1] = 0
                arr[j+2] = 0
                j = j+3
                #print('No hand landmarks detected.')

            # Store the landmarks data in the array
            data[i] = arr

            # Display the video with hand landmarks if DISPLAY is set to True
            if DISPLAY:
                image.flags.writeable = True
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                if results.multi_hand_landmarks:
                    for hand_landmarks in results.multi_hand_landmarks:
                        mp_drawing.draw_landmarks(
                            image,
                            hand_landmarks,
                            mp_hands.HAND_CONNECTIONS,
                            mp_drawing_styles.get_default_hand_landmarks_style(),
                            mp_drawing_styles.get_default_hand_connections_style())
                # Flip the image horizontally for a selfie-view display.
                cv2.imshow('MediaPipe Hands', cv2.flip(image, 1))
                if cv2.waitKey(5) & 0xFF == 27:
                    break

    # Release the video capture object
    cap.release()

    # Define column names for the dataframe
    cols = [ ('Mediapipe','WRIST', 'x'),             ('Mediapipe','WRIST', 'y'),            ('Mediapipe','WRIST', 'likelihood'), 
            ('Mediapipe','THUMB_CMC', 'x'),         ('Mediapipe','THUMB_CMC', 'y'),        ('Mediapipe','THUMB_CMC', 'likelihood'),
            ('Mediapipe','THUMB_MCP', 'x'),         ('Mediapipe','THUMB_MCP', 'y'),        ('Mediapipe','THUMB_MCP', 'likelihood'),
            ('Mediapipe','THUMB_IP', 'x'),          ('Mediapipe','THUMB_IP', 'y'),         ('Mediapipe','THUMB_IP', 'likelihood'),
            ('Mediapipe','THUMB_TIP', 'x'),         ('Mediapipe','THUMB_TIP', 'y'),        ('Mediapipe','THUMB_TIP', 'likelihood'),
            ('Mediapipe','INDEX_FINGER_MCP', 'x'),  ('Mediapipe','INDEX_FINGER_MCP', 'y'), ('Mediapipe','INDEX_FINGER_MCP', 'likelihood'),
            ('Mediapipe','INDEX_FINGER_PIP', 'x'),  ('Mediapipe','INDEX_FINGER_PIP', 'y'), ('Mediapipe','INDEX_FINGER_PIP', 'likelihood'),
            ('Mediapipe','INDEX_FINGER_DIP', 'x'),  ('Mediapipe','INDEX_FINGER_DIP', 'y'), ('Mediapipe','INDEX_FINGER_DIP', 'likelihood'),
            ('Mediapipe','INDEX_FINGER_TIP', 'x'),  ('Mediapipe','INDEX_FINGER_TIP', 'y'), ('Mediapipe','INDEX_FINGER_TIP', 'likelihood'),
            ('Mediapipe','MIDDLE_FINGER_MCP', 'x'), ('Mediapipe','MIDDLE_FINGER_MCP', 'y'), ('Mediapipe','MIDDLE_FINGER_MCP', 'likelihood'),
            ('Mediapipe','MIDDLE_FINGER_PIP', 'x'), ('Mediapipe','MIDDLE_FINGER_PIP', 'y'), ('Mediapipe','MIDDLE_FINGER_PIP', 'likelihood'),
            ('Mediapipe','MIDDLE_FINGER_DIP', 'x'), ('Mediapipe','MIDDLE_FINGER_DIP', 'y'), ('Mediapipe','MIDDLE_FINGER_DIP', 'likelihood'),
            ('Mediapipe','MIDDLE_FINGER_TIP', 'x'), ('Mediapipe','MIDDLE_FINGER_TIP', 'y'), ('Mediapipe','MIDDLE_FINGER_TIP', 'likelihood'),
            ('Mediapipe','RING_FINGER_MCP', 'x'),   ('Mediapipe','RING_FINGER_MCP', 'y'),   ('Mediapipe','RING_FINGER_MCP', 'likelihood'),
            ('Mediapipe','RING_FINGER_PIP', 'x'),   ('Mediapipe','RING_FINGER_PIP', 'y'),   ('Mediapipe','RING_FINGER_PIP', 'likelihood'),
            ('Mediapipe','RING_FINGER_DIP', 'x'),   ('Mediapipe','RING_FINGER_DIP', 'y'),   ('Mediapipe','RING_FINGER_DIP', 'likelihood'),
            ('Mediapipe','RING_FINGER_TIP', 'x'),   ('Mediapipe','RING_FINGER_TIP', 'y'),   ('Mediapipe','RING_FINGER_TIP', 'likelihood'),
            ('Mediapipe','PINKY_MCP', 'x'),         ('Mediapipe','PINKY_MCP', 'y'),         ('Mediapipe','PINKY_MCP', 'likelihood'),
            ('Mediapipe','PINKY_PIP', 'x'),         ('Mediapipe','PINKY_PIP', 'y'),         ('Mediapipe','PINKY_PIP', 'likelihood'),
            ('Mediapipe','PINKY_DIP', 'x'),         ('Mediapipe','PINKY_DIP', 'y'),         ('Mediapipe','PINKY_DIP', 'likelihood'),
            ('Mediapipe','PINKY_TIP', 'x'),         ('Mediapipe','PINKY_TIP', 'y'),         ('Mediapipe','PINKY_TIP', 'likelihood')]

    # Create a dataframe from the data array with the specified columns
    df = pd.DataFrame(data, columns=cols)
    df.columns = pd.MultiIndex.from_tuples(df.columns, names=['scorer','bodyparts','coords'])

    # Create the output directory if it doesn't exist
    if not os.path.exists('pose-2d'):
        os.mkdir('pose-2d')

    # Save the dataframe to an HDF5 file
    df.to_hdf('pose-2d/'+VIDEO_FILE+'.h5', key='df', mode='w')