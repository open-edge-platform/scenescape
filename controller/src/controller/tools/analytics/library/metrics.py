#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import math
import statistics
import sys

import numpy as np


class Track:
  """! Object for containing moving object track information. """
  def __init__(self, xvals, yvals, gids, fvals, trackID):
    """!
    @param   xvals    x axis object location.
    @param   yvals    y axis object location.
    @param   fvals    frames where the track locations is defined.
    @param   f_range  dict obj containing min and max frame in f_range.
    @param   trackID  id of the tracked object
    """
    self.x_values = xvals
    self.y_values = yvals
    self.gids = gids
    self.frames = fvals
    self.id = trackID
    return

def getGIDLocs(data):
  """! This function creates a map of gid of object tracks
  @param   data    track data
  @return  gidMap  map of gids
  """
  gidMap = {}
  for key in data.keys():
    for frame in data[key].keys():
      gid = data[key][frame]['id']
      if gid not in gidMap:
        gidMap[gid] = {frame: {'x': data[key][frame]['translation'][0], 'y': data[key][frame]['translation'][1]}}
      gidMap[gid].update({frame: {'x': data[key][frame]['translation'][0], 'y': data[key][frame]['translation'][1]}})

  return gidMap


def listMean(vec):
  """! Compute the mean of a list.
  @param   vec LIST.
  @return  FLOAT.
  """
  return sum(vec) / len(vec)


##########################################################################
# Compute Metrics Methods
##########################################################################
def associateTracks(gt_tracks, p_tracks):
  """! This is a greedy association in the sense that it accociates the
  predicted track with the ground truth track with the smallest MSE. Here
  the error is defined as the Euclidean distance between two points.
  @param   gt_tracks  DICT of ground truth Track objects indexed by object ID.
  @param   p_tracks   DICT of predicted Track objects indexed by object ID.
  @param   params     DICT of test parameters.
  @return  DICT of fused Track objects indexed by ground truth object ID.
  @return  DICT of predicted Track objects indexed by ground truth object ID.

  Note: This is not necessary if there is only one ground truth track. But the
  track fusing does simplify the overhead of handling multiple predicted tracks.

  Note: A better algorithms exist to solve this problem. For instance the
  Stonesoup library uses scipy.optimize.linear_sum_assigment() which is related
  to the Hungarian or Munkers algorithm.

  TODO: Use better method.
  """
  # associate tracks

  mse_dict = {}
  atracks = {}
  gt_ids = list(gt_tracks.keys())
  for ID in p_tracks.keys():
    mse_dict[ID] = {}
    for gt_id in gt_ids:
      atracks[gt_id] = []
      mse = getMSE(gt_tracks[gt_id], p_tracks[ID])
      if mse:
        mse_dict[ID][gt_id] = mse['euclidean_mse']
      else:
        mse_dict[ID][gt_id] = 0.0

  # assign tracks
  for ID in p_tracks.keys():
    m = sys.maxsize
    id = None
    for gt_id in gt_ids:
      if (mse_dict[ID][gt_id] != None) and (mse_dict[ID][gt_id] < m):
        id = gt_id
        m = mse_dict[ID][gt_id]
    if id != None:
      atracks[id].append(ID)

  # fuse the tracks if necessary
  false_dectections = {}
  ftracks = {}

  for gt_id in atracks:
    track_set = atracks[gt_id]

    tmp_track = Track([], [], [], [], gt_id)
    false_d = -1
    conflict_frames = {}

    while track_set != []:
      if gt_id in list(gt_tracks.keys()):
        length = len(gt_tracks[gt_id].frames)
        tmp_track, conflict_frames = fuseTracks(tmp_track, p_tracks[track_set[0]],
                                              conflict_frames, length, gt_id)
        track_set.pop(0)
        false_d += 1

    tmp_track = resolveConflictFrames(tmp_track, conflict_frames)
    ftracks[gt_id] = tmp_track
    false_dectections[gt_id] = false_d

  return ftracks, false_dectections

def fuseTracks(t1, t2, conflict_frames, length, gtID):
  """! Fuses two tracks from a single object into one track.
  @param   t1               Track object
  @param   t2               Track object
  @param   conflict_frames  DICT of frames and locations where locations are
                            defined in t1 and t2.
  @param   params           DICT of test parameters.
  @return  new_track        Track object resulting from fusing t1 and t2.
  @return  conflict_frames  DICT of frames and locations where locations are
  defined in t1 and t2.
  """

  new_track = Track([], [], [], [], gtID)
  for f in range(length):
    x_val = None
    y_val = None
    place_hold = "conflict"
    if (f in t1.frames) and (f not in t2.frames):
      idx = t1.frames.index(f)
      x_val = t1.x_values[idx]
      y_val = t1.y_values[idx]
    elif (f not in t1.frames) and (f in t2.frames):
      idx = t2.frames.index(f)
      x_val = t2.x_values[idx]
      y_val = t2.y_values[idx]
    elif (f in t1.frames) and (f in t2.frames):
      idx = t1.frames.index(f)
      jdx = t2.frames.index(f)
      if (t1.x_values[idx] is not None) and (t1.y_values[idx] is not None) \
              and ((t2.x_values[jdx] is None) or (t2.y_values[jdx] is None)):
        x_val = t1.x_values[idx]
        y_val = t1.y_values[idx]
      elif (t2.x_values[jdx] is not None) \
              and (t2.y_values[jdx] is not None) \
              and ((t1.x_values[idx] is None) or (t1.y_values[idx] is None)):
        x_val = t2.x_values[jdx]
        y_val = t2.y_values[jdx]
      elif (t1.x_values[idx] is not None) \
              and (t2.x_values[jdx] is not None) \
              and (t1.y_values[idx] is not None) \
              and (t2.y_values[jdx] is not None):
        conflict_frames = updateConflictValues(conflict_frames, t1, t2, f,
                                              idx, jdx, place_hold)
        # Dummy values that are not None
        x_val = place_hold
        y_val = place_hold
    if ((x_val is not None) and (y_val is not None)):
      new_track.frames.append(f)
      new_track.x_values.append(x_val)
      new_track.y_values.append(y_val)

  return new_track, conflict_frames

def resolveConflictFrames(tmp_track, conflict_frames):
  """! Defines the location in a fused track given conflicting locations in
  the tracks being fused.
  @param    tmp_track        Track object with unresolved location conflicts.
  @param    conflict_frames  DICT of frames and locations where locations are
  defined in t1 and t2.
  """
  for frame in conflict_frames.keys():
    idx = tmp_track.frames.index(frame)
    x_ave = listMean(conflict_frames[frame]['x'])
    y_ave = listMean(conflict_frames[frame]['y'])
    tmp_track.x_values[idx] = x_ave
    tmp_track.y_values[idx] = y_ave

  return tmp_track

def updateConflictValues(conflict_frames, t1, t2, f, idx, jdx, place_hold):
  """! Adds locations to conflictFames.
  @param   conflict_frames
  @param   t1               Track object of first track.
  @param   t2               Track object of second track.
  @param   idx              INT index of first tracks conflicted location values.
  @param   jdx              INT index of second tracks conflicted location values.
  @param   place_hold       STRING placeholder.
  @return  conflict_frames  DICT of frames and locations where locations are
  defined in t1 and t2.

  Note: This only works if fusing two tracks. Will produce incorrect results
  if fusing more than to tracks.

  TODO: Generalize this algorithm or replace.
  """
  if f not in conflict_frames:
    conflict_frames[f] = {"x":[], "y":[]}

  if t1.x_values[idx] != place_hold:
    conflict_frames[f]["x"].append(t1.x_values[idx])

  if t2.x_values[jdx] != place_hold:
    conflict_frames[f]["x"].append(t2.x_values[jdx])

  if t1.y_values[idx] != place_hold:
    conflict_frames[f]["y"].append(t1.y_values[idx])

  if t2.y_values[jdx] != place_hold:
    conflict_frames[f]["y"].append(t2.y_values[jdx])

  return conflict_frames


def getTrack(data, trackID):
  """! Get Track object
  @param data       Dictionary of the track data.
  @param params     Dictionary of the test parameters.
  @param sensor_id  String for the sensor ID.
  @param x_name     String x coordinate name.
  @param y_name     String y coordinate name.
  @param flip_y     Boolean defining whether or not to filp the y-axis.
  @return track     Track object.
  """
  frames = []
  x_vals = []
  y_vals = []
  gids = []

  for f in data.keys():
    # does not account for frames missing data
    x_val = None
    y_val = None
    gid_val = None
    if 'id' in data[f]:
      x_val = data[f]['translation'][0]
      y_val = data[f]['translation'][1]
      gid_val = data[f]['id']
    else:
      x_val = data[f]['x']
      y_val = data[f]['y']

    frames.append(f)
    x_vals.append(x_val)
    y_vals.append(y_val)
    gids.append(gid_val)
  track = Track(x_vals, y_vals, gids, frames, trackID)

  return track

def associateGIDs(pred_obj_tracks, gtTracks):
  """! Associate GIDs accross sensors. This assumes that the GID
  of a detected object will always be the same for all sensors.
  @param    pred_obj_tracks
  @param    params            DICT of test parameters.
  @return   ftracks           DICT of Track objects after GID association.

  Problem: This code calculates the mean of conflicting points in tracks with
  the same GID, then calculates the mean of conflicting points in tracks
  associated with same ground truth track. This second mean could be a mean of
  mean's and not a true mean.
  """

  # get tracks
  p_tracks = {}
  p_ids = list(pred_obj_tracks.keys())
  for p_id in p_ids:
    p_track = getTrack(pred_obj_tracks[p_id], p_id)
    p_tracks[p_id] = p_track

  # fuse the tracks if necessary
  ftracks = {}
  for id in gtTracks:
    for p_id in p_tracks:
      tmp_track = Track([], [], [], [], p_id)
      conflict_frames = {}
      length = len(gtTracks[id].frames)
      tmp_track, conflict_frames = fuseTracks(tmp_track,
                                              p_tracks[p_id],
                                              conflict_frames, length, p_id)
      tmp_track = resolveConflictFrames(tmp_track, conflict_frames)
      ftracks[p_id] = tmp_track

  return ftracks

def getMSE(gt_track, p_track):
  """! Compute the MSE between a predicted and an actual track.
  @param   gt_track  Ground truth Track object.
  @param   p_track   Predicted Track object.
  @param   params    Dictionary of test parameters.
  @return  Float MSE.

  Note: This only computes the MSE between frames where object location is
  defined in the ground truth and the predicted track. Also since there is
  not a standard definition for the MSE between multivariate variables I
  decided to break out the MSE for the individual dimensions as well as the
  distance between the predicted and expected points.
  """
  x_mse = 0
  y_mse = 0
  euclidean_mse = 0
  manhattan_mse = 0

  cFrames = set(gt_track.frames).intersection(set(p_track.frames))
  n = 0

  for f in list(cFrames):
    adx = gt_track.frames.index(f)
    pdx = p_track.frames.index(f)

    if (p_track.x_values[pdx] is not None) and (p_track.y_values[pdx] is not None):
      # change coord system
      # for GT y
      gt_y = gt_track.y_values[adx]
      p_y = p_track.y_values[pdx]

      x_err = gt_track.x_values[adx] - p_track.x_values[pdx]
      y_err = gt_y - p_y

      manhattan_dist = abs(x_err) + abs(y_err)
      euclidean_dist = math.sqrt(math.pow(x_err, 2) + math.pow(y_err, 2))

      x_mse += math.pow(x_err, 2)
      y_mse += math.pow(y_err, 2)
      manhattan_mse += math.pow(manhattan_dist, 2)
      euclidean_mse += math.pow(euclidean_dist, 2)
      n += 1

  mse = {}
  if n != 0:
    mse['x_mse'] = x_mse / n
    mse['y_mse'] = y_mse / n
    mse['manhattan_mse'] = manhattan_mse / n
    mse['euclidean_mse'] = euclidean_mse / n
    return mse
  else:
    return None

def setTimelapsed(trackData):
  """Populate the predicted track data with computed time elapsed
  @param   trackData  predicted track data object to be populated
  """
  timeElapsed = None

  for data in trackData:
    _, minutes, seconds = data['timestamp'].split(':')
    seconds, millisec = seconds.strip('Z').split('.')
    timeElapsedMilliSec = int(minutes)*60*1000 + int(seconds)*1000 + int(millisec)
    data['timeElapsedMilliSec'] = timeElapsedMilliSec
  return

def closest(gtTimeElapsed, predTimeElapsed):
  """Find event closest to current event, wrt time elapsed, in ground truth data
  @param   gtData     Ground truth json data.
  @param   predData   Predictions json data.
  @return  Float MICE.
  """
  key = gtTimeElapsed[min(range(len(gtTimeElapsed)), key = lambda i: abs(gtTimeElapsed[i][0] - predTimeElapsed))]
  index = 0

  for li in range(len(gtTimeElapsed)):
    if gtTimeElapsed[li][1] == True and gtTimeElapsed[li][0] == key[0]:
      continue
    elif gtTimeElapsed[li][1] == False and gtTimeElapsed[li][0] == key[0]:
      gtTimeElapsed[li][1] = True
      index = li
      break

  return index

def groupDataByTime(predData):
  """
  This function re-arranges predictions json data by grouping outputs for all camera frames at a specific timestamps
  @param      predData            Predictions json data
  @return     predDataModified    Predictions json data fter re-grouping
  """
  predDataModified = [predData[0]]
  for i in range(1, len(predData)):
    if predData[i]['timestamp'] == predData[i-1]['timestamp']:
      item = predDataModified.pop()
      alreadySeenObj = [obj['id'] for obj in item['objects']]
      for obj in predData[i]['objects']:
        if obj['id'] not in alreadySeenObj:
          item['objects'].append(obj)
      if isinstance(item['cam_id'], list):
        item['cam_id'].append(predData[i]['cam_id'])
      else:
        item['cam_id'] = [item['cam_id'], predData[i]['cam_id']]
      predDataModified.append(item)
    else:
      predDataModified.append(predData[i])
  return predDataModified

def getVelocity(predData):
  """This functions returns the max and standard deviation velocity from
  the prediction json data
  @param   predData         Predictions json data.
  @return  max_velocity     The maximum velocity of the tracked objects.
  @return  std_velocity     The standard deviation velocity from the tracked objects.
  """

  velocity = []
  std_velocity = None
  max_velocity = None

  for data in predData:
    for obj in data['objects']:
      if 'velocity' in obj:
        magnitude = math.sqrt(obj['velocity'][0] ** 2 + \
                                obj['velocity'][1] ** 2 + \
                                obj['velocity'][2] ** 2)
        velocity.append(magnitude)

  if velocity:
    std_velocity = np.std(velocity)
    max_velocity = np.max(velocity)

  return max_velocity, std_velocity

def getMeanSquareObjCountError(gtData, predData):
  """Given Ground Truth and Predicted tracker data as inputs,
  calculates mean square object count error.
  @param   gtData       Ground truth json data.
  @param   predData     Predictions json data.
  @return  Float MSOCE.

  Note: errors that cause MSOCE:
  1. Duplications
  2. Ghost detections
  3. Tracking objects that have left FOV"""
  setTimelapsed(gtData)
  setTimelapsed(predData)
  predDataMod = groupDataByTime(predData)
  ocErrorSquared = []
  gtTimeElapsed = [[gt['timeElapsedMilliSec'], False] for gt in gtData]

  for i, data in enumerate(predDataMod):
    predTimeElapsed = data['timeElapsedMilliSec']
    index = closest(gtTimeElapsed, predTimeElapsed)
    gtObjectCount = 0
    for _, objects in gtData[index]["objects"].items():
      gtObjectCount += len(objects)
    predObjectCount = len(data["objects"])
    ocErrorSquared.append((gtObjectCount - predObjectCount)**2)

  return statistics.mean(ocErrorSquared)

def computeRealIdChange(gtIds, predIds, lastGtIds, lastPredIds):
  """Compute Id change error from last frame to cur frame
  @param   gtData      Ground truth json data.
  @param   predData    Predictions json data.
  @return  Float       Id change error.
  """
  predNewIdsCount = sum([0 if id in lastPredIds else 1 for id in predIds])
  fpDupContribution = max(0, len(predIds) - len(gtIds)) - \
    max(0, len(lastPredIds) - len(lastGtIds))
  newGtObjContribution = max(0, len(gtIds) - len(lastGtIds))

  return predNewIdsCount - fpDupContribution - newGtObjContribution

def getMeanIdChangeErrors(gtData, predData):
  """Given Ground Truth and Predicted tracker data as inputs,
  calculates temporal id change metric.
  @param   gtData       Ground truth json data.
  @param   predData     Predictions json data.
  @return  Float MICE.
  """
  setTimelapsed(gtData)
  setTimelapsed(predData)
  gtTimeElapsed = [[gt['timeElapsedMilliSec'], False] for gt in gtData]
  predDataMod = groupDataByTime(predData)
  idChangeErrors = []
  for i, data in enumerate(predDataMod):
    if i == 0:
      idChangeErrors.append(0)
      predTimeElapsed = data['timeElapsedMilliSec']
      index = closest(gtTimeElapsed, predTimeElapsed)
      lastGtIds = []
      for _, objects in gtData[index]["objects"].items():
        lastGtIds += [obj["id"] for obj in objects]
      try:
        lastPredIds = []
        for _, objects in data["objects"]:
          lastPredIds += [obj["id"] for obj in objects]
      except IndexError:
        pass
    else:
      try:
        predTimeElapsed = data['timeElapsedMilliSec']
        index = closest(gtTimeElapsed, predTimeElapsed)
        gtIds = []
        for _, objects in gtData[index]["objects"].items():
          gtIds += [obj["id"] for obj in objects]
        predIds = [obj["id"] for obj in data["objects"]]
        idChangeErrors.append(computeRealIdChange(gtIds, predIds, lastGtIds, lastPredIds))
        lastGtIds = gtIds
        lastPredIds = predIds
      except IndexError:
        pass

  return statistics.mean(idChangeErrors)
