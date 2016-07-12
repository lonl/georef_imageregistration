


import os, sys
import optparse
import sqlite3
#from pysqlite2 import dbapi2 as sqlite3

import registration_common
import register_image
import traceback

import dbLogger
import source_database
import offline_config
import georefDbWrapper
import IrgGeoFunctions

'''
This tool monitors for images which are finished processing
and generates the output files for them.
'''

# TODO: There are some duplicates with backlog_processor


def findReadyImages(options, georefDb, numImages):
    '''Get the next image which is ready to process'''

    if options.frame:
        return [(options.mission, options.roll, options.frame)]

    imageList = georefDb.getImagesReadyForOutput(limit=numImages)

    return imageList


def getImageRegistrationInfo(frameDbData, georefDb):
    '''Get information for the specified image'''
        
    # Retrieve needed image info from our DB
    registrationResult = georefDb.getRegistrationResult(frameDbData.mission, frameDbData.roll, frameDbData.frame)
    
    # This function generates/fetches the source image if it does not exist
    registrationResult['sourceImagePath'] = source_database.getSourceImage(frameDbData)
    
    return registrationResult

def correctPixelCoordinates(registrationResult):
    '''Rescales the pixel coordinates based on the resolution they were collected at
       compared to the full image resolution.'''
       
    # TODO: Account for the image side labels adjusting the image size!

    sourceHeight = registrationResult['manualImageHeight']
    sourceWidth  = registrationResult['manualImageWidth' ]
    
    (outputWidth, outputHeight) = IrgGeoFunctions.getImageSize(registrationResult['sourceImagePath'])

    if (sourceHeight != outputHeight) or (sourceWidth != outputWidth):

        # Compute rescale
        heightScale = float(outputHeight) / float(sourceHeight)
        widthScale  = float(outputWidth)  / float(sourceWidth)

        # Apply to each of the pixel coordinates
        out = []
        for pixel in registrationResult['imageInliers']:
            newPixel = (pixel[0]*widthScale, pixel[1]*heightScale)
            out.append(newPixel)
        registrationResult['imageInliers'] = out
    
    return registrationResult

def getOutputPrefix(mission, roll, frame):
    '''Return the output prefix for this frame'''
    
    filePath = registration_common.getWorkingPath(mission, roll, frame)
    prefix   = os.path.splitext(filePath)[0]
    
    return prefix


def main(argsIn):

    try:
        usage = "usage: output_generator.py [--help]\n  "
        parser = optparse.OptionParser(usage=usage)
        
        parser.add_option("--mission", dest="mission", default=None,
                          help="Specify a mission to process.")
        parser.add_option("--roll",    dest="roll",    default=None,
                          help="Specify a roll to process.  Requires mission.")
        parser.add_option("--frame",   dest="frame",   default=None,
                          help="Specify a frame to process. Requires roll.")
        
        parser.add_option("--limit",   dest="limit",   default=0, type="int",
                          help="Do not process more than this many frames.")

        (options, args) = parser.parse_args(argsIn)

        if ((options.mission or options.roll or options.frame) and 
            not (options.mission and options.roll and options.frame)):
            raise Exception('mission/roll/frame must be provided together!')
            
    except optparse.OptionError, msg:
        raise Usage(msg)

    print '---=== Output Generator has started ===---'


    print 'Connecting to our database...'
    
    # TODO: Turn the input DB into a full wrapper.
    sourceDb = sqlite3.connect(offline_config.DB_PATH)
    sourceDbCursor = sourceDb.cursor()
    georefDb = georefDbWrapper.DatabaseLogger()
    

    # Get images to process
    targetFrames = findReadyImages(options, georefDb, options.limit)

    if len(targetFrames) == 0:
        print 'Did not find any frames ready to process.'

    count = 0
    for (mission, roll, frame) in targetFrames:

        try:
            print str((mission, roll, frame))
            
            frameDbData = source_database.FrameInfo()
            frameDbData.loadFromDb(sourceDbCursor, mission, roll, frame)
            print 'Output Generator obtained data: ' + str(frameDbData)

            # Get the registration info for this image, then apply manual pixel coord correction.
            imageRegistrationInfo = getImageRegistrationInfo(frameDbData, georefDb)
            if imageRegistrationInfo['isManual']:
                imageRegistrationInfo = correctPixelCoordinates(imageRegistrationInfo)
    
            outputPrefix = getOutputPrefix(mission, roll, frame)
        
            registration_common.recordOutputImages(imageRegistrationInfo['sourceImagePath'], outputPrefix,
                                                   imageRegistrationInfo['imageInliers'],
                                                   imageRegistrationInfo['gdcInliers'],
                                                   imageRegistrationInfo['registrationMpp'],
                                                   imageRegistrationInfo['isManual'], overwrite=True)
            
            # Clean up the source image we generated
            os.remove(imageRegistrationInfo['sourceImagePath'])
            
            # Update the database to record that we wrote the image
            georefDb.markAsWritten(mission, roll, frame)

            break # DEBUG!

        except Exception as e:
            print 'Caught exception:'
            print(sys.exc_info()[0])
            print traceback.print_exc()
            
        count += 1

    print '---=== Output Generator has stopped ===---'
    

#def test():


# Simple test script
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))