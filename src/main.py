import numpy as np
import cv2
import argparse
import logging
from input_feeder import InputFeeder
from faceDetection import FaceDetection
from faceMaskDetection import MaskDetection
from personDetection import PersonDetect
from safetyGear import GearDetect
import time
import os

CPU_EXTENSION="/opt/intel/openvino/deployment_tools/inference_engine/lib/intel64/libcpu_extension_sse4.so"

logging.basicConfig(filename='safety.log', level=logging.DEBUG)

def get_args():
    '''
    This function gets the arguments from the command line.
    '''

    parser = argparse.ArgumentParser()
    
    # --Add required and optional groups
    required = parser.add_argument_group('required arguments')
    optional = parser.add_argument_group('optional arguments')

    # --create the arguments
    optional.add_argument("-m_f", help="path to face detection model", default='./models/face-detection-adas-binary-0001')
    optional.add_argument("-m_m", help="path to mask detection model", default='./models/face_mask')
    optional.add_argument("-m_p", help="path to person detection model", default='./models/person-detection-retail-0013/FP16/person-detection-retail-0013')
    optional.add_argument("-m_g", help="path to safety gear detection model", default="./models/worker-safety-mobilenet/worker_safety_mobilenet")

    '''
    required.add_argument("-m_f",help="path to face detection model", required=True)
    required.add_argument("-m_m",help="path to mask detection model", required=True)
    required.add_argument("-m_p",help="path to person detection model", required=True)
    required.add_argument("-m_g",help="path to safety gear detection model", required=True)
    '''
    required.add_argument("-i", help="path to video/image file or 'cam' for webcam", required=True)

    optional.add_argument("-l", help="MKLDNN (CPU)-targeted custom layers.", default=CPU_EXTENSION, required=False)
    optional.add_argument("-d", help="Specify the target device type", default='CPU')
    optional.add_argument("-p", help="path to store performance stats", required=False)
    optional.add_argument("-ps", help="specify flags from 1, 2, (select a prediction flag)", default='3')

    args = parser.parse_args()
    return args


# pred_switch = args.ps
def pipelines(args):
    '''
    This function writes perfomance status of each model used to a txt file.
    '''
    # enable logging for the function
    logger = logging.getLogger(__name__)

    
    
    # grab the parsed parameters
    faceDetectionModel=args.m_f
    maskDetectionModel=args.m_m
    personDetectionModel=args.m_p
    gearDetectionModel=args.m_g
    device=args.d
    customLayers=args.l
    inputFile=args.i
    pred_switch=args.ps
    
    
    # initialize feed
    single_image_format = ['jpg','tif','png','jpeg', 'bmp']
    if inputFile.split(".")[-1].lower() in single_image_format:
        feed=InputFeeder('image',inputFile)
    elif args.i == 'cam':
        feed=InputFeeder('cam')
    else:
        feed = InputFeeder('video',inputFile)

    # Create a video writer for the output video
    # The second argument should be `cv2.VideoWriter_fourcc('M','J','P','G')`
    # on Mac, and `0x00000021` on Linux
    # out = cv2.VideoWriter('out.mp4', cv2.VideoWriter_fourcc('M','J','P','G'), 10, (1920,1080)) 
    # fourcc = cv2.VideoWriter_fourcc(*'XVID')
    # out = cv2.VideoWriter('out.mp4',fourcc,10,(1920,1080))   
    
    # load feed data
    feed.load_data()

    # initialize and load the models
    ## load the face detection model 
    faceDetectionPipeline=FaceDetection(faceDetectionModel, device, customLayers)
    faceDetectionPipeline.load_model()

    # load the face mask model
    maskDetectionPipeline=MaskDetection(maskDetectionModel, device, customLayers)
    maskDetectionPipeline.load_model()

    # load the person detection model
    personDetectionPipeline=PersonDetect(personDetectionModel, device, customLayers)
    personDetectionPipeline.load_model()

    # load the hard hat and safety jacket    
    gearDetectionPipeline=GearDetect(gearDetectionModel, device, customLayers)
    gearDetectionPipeline.load_model()
    

     # set framecount, request_id, infer_handle variables
    frameCount = 0

    # collate frames from the feeder and feed into the detection pipelines
    for _, frame in feed.next_batch():
        if not _:
            break
        frameCount+=1
        
        # wait before interrupting on keyboard event
        key = cv2.waitKey(60)

        height = frame.shape[0]
        width = frame.shape[1]
        
        # start person detection
        personCoords, personFlag = personDetectionPipeline.predict(frame.copy())
        
        # break, if no person is in view
        if personFlag ==True:
            logger.info("Person detected")
            
            # Use the coordinates from personCoords to crop the person
            # personCoords is an array with the indexes giving x0,y0,x1,y1 respectively
            for _ in personCoords:
                x0,y0,x1,y1=_
                padding = 40
                xmin = int(x0 * width)
                ymin = int(y0 * height)
                xmax = int(x1 * width)
                ymax = int(y1 * height)
                xmin = int(xmin - padding) if (xmin - padding) > 0 else 0
                ymin = int(ymin - padding) if (ymin - padding) > 0 else 0
                xmax = int(xmax + padding) if (xmax + padding) <  width else  width
                ymax = int(ymax + padding) if (ymax + padding) <  height else  height

                croppedperson = frame[ymin:ymax,xmin:xmax] 
                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (255, 255, 255), 2)

                c_height = croppedperson.shape[0]
                c_width =croppedperson.shape[1]

                detection_list = []
                if pred_switch == "1" or pred_switch == "3":
                    # feed the cropped person into the hard hat and safety vest model i.e. GearDetect
                    vest_flag, helment_flag, vest, helment = gearDetectionPipeline.predict(croppedperson.copy())

                    # check if the coords gotten from the hard hat and safety vest model, i.e. GearDetect, is empty 
                    # as a means to check if someone is present with a hard hat or safety vest
                    
                        # if someone is with a safety kit, normalize the coords and append it to the detction list
                            # Using ths coordinates of the kit on the person 
                            # draw and label the person's compliance with either hard hat or vest
                    for _ in helment:
                        h_x0,h_y0,h_x1,h_y1=_
                        xmin_h = int(h_x0 * c_width)
                        ymin_h = int(h_y0 * c_height)
                        xmax_h = int(h_x1 * c_width)
                        ymax_h = int(h_y1 * c_height)
                        if vest_flag == True:
                            logger.info("vest detected")
                            cv2.rectangle(croppedperson, (xmin_h, ymin_h), (xmax_h, ymax_h), (0, 255, 0), 2)
                            # cv2.putText(croppedperson,"helment", (xmin_h-2, ymin_h), cv2.FONT_HERSHEY_COMPLEX, 0.8, (0,255,0),1)

                    for _ in vest:
                        v_x0,v_y0,v_x1,v_y1=_
                        xmin_v = int(v_x0 * c_width)
                        ymin_v = int(v_y0 * c_height)
                        xmax_v = int(v_x1 * c_width)
                        ymax_v = int(v_y1 * c_height)
                        
                        if vest_flag == True:
                            logger.info("gear detected")
                            cv2.rectangle(croppedperson, (xmin_v, ymin_v), (xmax_v, ymax_v), (0, 255, 0), 2)
                            # cv2.putText(croppedperson,"vest", (xmin_v-2, ymin_v), cv2.FONT_HERSHEY_COMPLEX, 0.8, (0,255,0),1)


        if pred_switch == "2" or pred_switch == "3":

            # send the frame to the face detection pipeline
            faceCoords, faceFlag=faceDetectionPipeline.predict(frame.copy())
            # if there is a face, obtain the coordinates of the face and send the face
            # to the mask detection pipeline
            if faceFlag ==True:
                for _ in faceCoords:
                    x0,y0,x1,y1=_

                    xmin_m = int((x0 * width)-10)
                    ymin_m = int((y0 * height)-5)
                    xmax_m = int((x1 * width))
                    ymax_m = int((y1 * height)-10)
                    
                    croppedFace = frame[ymin_m:ymax_m,xmin_m:xmax_m]
                    # output frame for showing inferencing results 
                    # out_cv = frame.copy()

                    # # draw outlines of the face
                    cv2.rectangle(frame, (xmin_m, ymin_m), (xmax_m, ymax_m), (255, 255, 255), 2)
                    mask_detect = maskDetectionPipeline.predict(croppedFace.copy())
                
                    if mask_detect < 0:                    
                        cv2.putText(frame,"No mask detected", (xmin_m -2, ymin_m), cv2.FONT_HERSHEY_COMPLEX, 0.8, (0,0,255),1)
                    elif mask_detect > 0:
                        logger.info("mask detected")
                        cv2.putText(frame,"Mask detected", (xmin_m -2, ymin_m), cv2.FONT_HERSHEY_COMPLEX, 0.8, (0,255,0),1)
        
        
        # visualize the video
        cv2.imshow('mask', frame)
        # out.write(frame)
        if key & 0xFF == ord('q'):
            break
    
    
    logger.info("The End")
    cv2.destroyAllWindows()
    # out.release()
    feed.close()
    

def main():
    args=get_args()
    pipelines(args)

    

if __name__ == '__main__':
    main()