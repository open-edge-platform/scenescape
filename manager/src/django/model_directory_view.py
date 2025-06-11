# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.
import os
import shutil
import zipfile

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework import authentication
from rest_framework import status
from rest_framework.views import APIView

from manager.views import IsAdminOrReadOnly

# Authenticated with sessionid and csrf token
class ModelDirectory(APIView):
  authentication_classes = [authentication.SessionAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  # Safely join paths and ensure they are within MODEL_ROOT
  # returns (joined_path, error_message)
  def safePathJoin(self, *args):
    joined_path = os.path.join(*args)
    # Check if the normalized path is still within MODEL_ROOT
    norm_path = os.path.normpath(joined_path)
    norm_model_root = os.path.normpath(settings.MODEL_ROOT)
    if not norm_path.startswith(norm_model_root):
      return None, "Invalid path"
    return norm_path, None

  # Load the directory and return directory content in html format
  # return data, status_code
  def loadDirectory(self, path, folder_name):

    # Error handling
    if(path is None):
      return 'No path provided', status.HTTP_400_BAD_REQUEST
    if(folder_name is None or folder_name == ''):
      return 'No folder name provided', status.HTTP_400_BAD_REQUEST

    # Get the full path of the directory
    full_path, error = self.safePathJoin(settings.MODEL_ROOT, path, folder_name)
    if error:
      return 'Invalid path', status.HTTP_400_BAD_REQUEST

    # return error if the path exists
    if not os.path.exists(full_path):
      return 'Path not found. It may have been deleted. Please refresh the page.', status.HTTP_404_NOT_FOUND

    # Initialize the directory structure with the folder or file
    dir_structure = {}
    if os.path.isfile(full_path): # File case
      dir_structure[folder_name] = None
    else: # Directory case - load its subdirectory content
      dir_structure[folder_name] = {}

      # Walk through the directory and load its content
      for dirpath, dirnames, filenames in os.walk(full_path):
        # Sort the directories and files alphabetically
        dirnames.sort(key=lambda s: s.lower())
        filenames.sort(key=lambda s: s.lower())

        # Get the relative path of the directory
        folder = os.path.relpath(dirpath, full_path)

        # Reset the current level to the directory structure to requested folder
        current_level = dir_structure[folder_name]

        if folder != '.': # if not root folder
          for part in folder.split(os.sep):
            # Enter deeper level if the current directory exists in the dictionary
            # Otherwise, create a new entry for the directory
            current_level = current_level.setdefault(part, {})

        # Load all directory to the current level
        for dirname in dirnames:
          current_level[dirname] = {}

        # Load all file to the current level
        for filename in filenames:
          current_level[filename] = None

    # Ensure the format is correct
    # eg. path/to/directory/
    if path == "" or path.endswith('/'):
      pass
    else:
      path = path + '/'

    # Count depth level
    depth_level = len([part for part in os.path.join(path, folder_name).split(os.sep) if part])

    # Render the directory content in html format
    html = render_to_string('model/includes/model_directory.html', {
        'path': path,
        'directory_structure': dir_structure,
        'depth': 16 + 32 * depth_level,
    })
    return html, status.HTTP_200_OK

  # Check if the directory exists
  # return data, status code
  def checkDirectoryExistence(self, path, folder_name):
    if path is None:
      return 'No path provided', status.HTTP_400_BAD_REQUEST
    if folder_name is None or folder_name == '':
      return 'No folder name provided', status.HTTP_400_BAD_REQUEST

    full_path, error = self.safePathJoin(settings.MODEL_ROOT, path, folder_name)
    if error:
      return 'Invalid path', status.HTTP_400_BAD_REQUEST

    if os.path.exists(full_path):
      return True, status.HTTP_200_OK
    else:
      return False, status.HTTP_200_OK

  # Create directory
  # return data, status code
  def createDirectory(self, path, new_folder_name):
    if path is None:
      return 'No path provided', status.HTTP_400_BAD_REQUEST
    if new_folder_name is None or new_folder_name == '':
      return 'No directory name provided', status.HTTP_400_BAD_REQUEST

    try:
      mkdir, error = self.safePathJoin(settings.MODEL_ROOT, path, new_folder_name)
      if error:
        return 'Invalid path', status.HTTP_400_BAD_REQUEST

      # Check if the directory already exists
      if os.path.exists(mkdir):
        return 'Directory already exists', status.HTTP_409_CONFLICT

      # Create the folder at requested path
      os.makedirs(mkdir, exist_ok=True)
      return 'Directory created successfully', status.HTTP_201_CREATED
    except Exception as e:
      return f'Error creating directory: {str(e)}', status.HTTP_500_INTERNAL_SERVER_ERROR

  # Extract a zip file to the specified directory
  # return data, file_set, status code
  def extractZipFileToDirectory(self, path, zip_file):
    if path is None:
      return 'No path provided', status.HTTP_400_BAD_REQUEST
    if zip_file is None:
      return 'No file is uploaded', status.HTTP_400_BAD_REQUEST

    # Define the directory where the file should be saved
    save_path, error = self.safePathJoin(settings.MODEL_ROOT, path)
    if error:
      return 'Invalid path', status.HTTP_400_BAD_REQUEST

    try:
      if zip_file.name.endswith('.zip'): # zip file case
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
          zip_ref.extractall(save_path)
        return 'ZIP file extracted and uploaded successfully', status.HTTP_200_OK
      else:
        return 'Invalid file type', status.HTTP_400_BAD_REQUEST
    except Exception as e:
      return f'Error uploading file: {str(e)}', status.HTTP_500_INTERNAL_SERVER_ERROR

  # Upload a file to the specified directory
  # return data, status code
  def uploadFileToDirectory(self, path, uploaded_file):
    if path is None:
      return 'No path provided', status.HTTP_400_BAD_REQUEST
    if uploaded_file is None:
      return 'No file is uploaded', status.HTTP_400_BAD_REQUEST

    # Define the directory where the file should be saved
    save_path, error = self.safePathJoin(settings.MODEL_ROOT, path)
    if error:
      return 'Invalid path', status.HTTP_400_BAD_REQUEST

    try:
      file_path, error = self.safePathJoin(save_path, uploaded_file.name)
      if error:
        return 'Invalid path', status.HTTP_400_BAD_REQUEST
      # Save the file to the specified directory
      with open(file_path, 'wb+') as destination:
        for chunk in uploaded_file.chunks():
          destination.write(chunk)

      return 'File uploaded successfully', status.HTTP_200_OK
    except Exception as e:
      return f'Error uploading file: {str(e)}', status.HTTP_500_INTERNAL_SERVER_ERROR

  def deleteDirectory(self, path, delete_folder_name):
    if path is None:
      return 'No path provided', status.HTTP_400_BAD_REQUEST
    if delete_folder_name is None or delete_folder_name == '':
      return 'No folder name provided', status.HTTP_400_BAD_REQUEST

    delete_path, error = self.safePathJoin(settings.MODEL_ROOT, path, delete_folder_name)
    if error:
      return 'Invalid path', status.HTTP_400_BAD_REQUEST

    try:
      if os.path.isfile(delete_path): # file case
        os.remove(delete_path)
        return 'File deleted successfully', status.HTTP_200_OK
      elif os.path.islink(delete_path): # symbolic link case
        os.unlink(delete_path)
        return 'Symbolic link deleted successfully', status.HTTP_200_OK
      elif os.path.exists(delete_path): # directory case
        shutil.rmtree(delete_path)
        return 'Directory deleted successfully', status.HTTP_200_OK
      else:
        return 'Path not found. It may have been deleted. Please refresh the page.', status.HTTP_404_NOT_FOUND
    except Exception as e:
      return f'Error deleting file: {str(e)}', status.HTTP_500_INTERNAL_SERVER_ERROR

  def get(self, request):
    action = request.GET.get('action')
    path = request.GET.get('path')
    folder_name = request.GET.get('folder_name')

    if action == "check":
      data, status_code = self.checkDirectoryExistence(path, folder_name)
      return HttpResponse(data, status=status_code)
    elif action == "load":
      data, status_code = self.loadDirectory(path, folder_name)
      return HttpResponse(data, status=status_code)
    else:
      return HttpResponse('Invalid action', status=status.HTTP_400_BAD_REQUEST)

  def post(self, request):

    path = request.POST.get('path')
    action = request.POST.get('action')

    if action == "create":
      new_folder_name = request.POST.get('folder_name')
      data, status_code = self.createDirectory(path, new_folder_name)
      return HttpResponse(data, status=status_code)
    elif action == "upload" :
      file = request.FILES.get('file')
      data, status_code = self.uploadFileToDirectory(path, file)
      return HttpResponse(data, status=status_code)
    elif action == "extract":
      zip_file = request.FILES.get('file')
      data, status_code = self.extractZipFileToDirectory(path, zip_file)
      return HttpResponse(data, status=status_code)
    else:
      return HttpResponse('Invalid action', status=status.HTTP_400_BAD_REQUEST)

  def delete(self, request):
    path = request.POST.get('path')
    delete_folder = request.POST.get('folder_name')
    data, status_code = self.deleteDirectory(path, delete_folder)
    return HttpResponse(data, status=status_code)
