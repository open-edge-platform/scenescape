// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

"use strict";

import {
  MODEL_DIRECTORY_API,
  DIRECTORY_LEFT_INDENT,
} from "/static/js/constants.js";

$(document).ready(function () {
  // Call model-directory GET API (load) to get the list of files in the directory
  // path format - path/to/directory/
  function loadModelDirectoryFiles(path, folder_name) {
    return new Promise((resolve, reject) => {
      let url = MODEL_DIRECTORY_API;

      var formData = new FormData();
      formData.append("path", path);
      formData.append("action", "load");
      formData.append("folder_name", folder_name);

      const queryParams = new URLSearchParams(formData).toString();
      url += `?${queryParams}`;

      $.ajax({
        url: url,
        headers: {
          "X-CSRFToken": $("input[name=csrfmiddlewaretoken]").val(),
        },
        type: "GET",
        data: null,
        processData: false,
        contentType: false,
        success: function (response) {
          resolve(response);
        },
        error: function (xhr, status, error) {
          reject(`${xhr.responseText || status}`);
        },
      });
    });
  }

  // Call model-directory GET API (check) to check file existence
  // path format - path/to/directory/
  function checkDirectoryExistence(path, folder_name) {
    return new Promise((resolve, reject) => {
      let url = MODEL_DIRECTORY_API;

      var formData = new FormData();
      formData.append("path", path);
      formData.append("action", "check");
      formData.append("folder_name", folder_name);

      const queryParams = new URLSearchParams(formData).toString();
      url += `?${queryParams}`;

      $.ajax({
        url: url,
        headers: {
          "X-CSRFToken": $("input[name=csrfmiddlewaretoken]").val(),
        },
        type: "GET",
        data: null,
        processData: false,
        contentType: false,
        success: function (response) {
          if (response === "False" || response === false) {
            resolve(false);
          } else {
            resolve(true);
          }
        },
        error: function (xhr, status, error) {
          reject(`${xhr.responseText || status}`);
        },
      });
    });
  }

  // Call model-directory POST API (create) to create a new folder
  // path format - path/to/directory/
  function createModelDirectory(path, new_folder_name) {
    return new Promise((resolve, reject) => {
      let url = MODEL_DIRECTORY_API;

      var formData = new FormData();
      formData.append("path", path);
      formData.append("action", "create");
      formData.append("folder_name", new_folder_name);

      $.ajax({
        url: url,
        headers: {
          "X-CSRFToken": $("input[name=csrfmiddlewaretoken]").val(),
        },
        type: "POST",
        data: formData,
        processData: false,
        contentType: false,
        success: function (response, status, xhr) {
          resolve(response);
        },
        error: function (xhr, status, error) {
          reject(`${xhr.responseText || status}`);
        },
      });
    });
  }

  // Call model-directory POST API (upload) to upload file
  // path format - path/to/directory/
  // uploaded_file - file object
  function uploadModelDirectoryFile(path, uploaded_file) {
    return new Promise((resolve, reject) => {
      let url = MODEL_DIRECTORY_API;

      var formData = new FormData();
      formData.append("path", path);
      formData.append("action", "upload");
      formData.append("file", uploaded_file);

      $.ajax({
        url: url,
        headers: {
          "X-CSRFToken": $("input[name=csrfmiddlewaretoken]").val(),
        },
        type: "POST",
        data: formData,
        processData: false,
        contentType: false,
        beforeSend: function () {
          // Show loading spinner
          showLoadingSpinner();
        },
        success: function (response) {
          resolve(response);
        },
        error: function (xhr, status, error) {
          reject(`${xhr.responseText || status}`);
        },
        complete: function () {
          // Hide loading spinner
          hideLoadingSpinner();
        },
      });
    });
  }
  // Call model-directory POST API (extract) to extract a file
  // path format - path/to/directory/
  // uploaded_file - file object (zip file)
  function extractModelDirectoryFile(path, uploaded_file) {
    return new Promise((resolve, reject) => {
      let url = MODEL_DIRECTORY_API;

      var formData = new FormData();
      formData.append("path", path);
      formData.append("action", "extract");
      formData.append("file", uploaded_file);

      $.ajax({
        url: url,
        headers: {
          "X-CSRFToken": $("input[name=csrfmiddlewaretoken]").val(),
        },
        type: "POST",
        data: formData,
        processData: false,
        contentType: false,
        beforeSend: function () {
          showLoadingSpinner();
        },
        success: function (response) {
          resolve(response);
        },
        error: function (xhr, status, error) {
          reject(`${xhr.responseText || status}`);
        },
        complete: function () {
          hideLoadingSpinner();
        },
      });
    });
  }

  // Call model-directory DELETE API to delete a directory
  // path format - path/to/directory/
  function deleteModelDirectory(path, folder_name) {
    return new Promise((resolve, reject) => {
      let url = MODEL_DIRECTORY_API;

      var formData = new FormData();
      formData.append("path", path);
      formData.append("folder_name", folder_name);

      $.ajax({
        url: url,
        headers: {
          "X-CSRFToken": $("input[name=csrfmiddlewaretoken]").val(),
        },
        type: "DELETE",
        data: formData,
        processData: false,
        contentType: false,
        success: function (response) {
          resolve(response);
        },
        error: function (xhr, status, error) {
          reject(`${xhr.responseText || status}`);
        },
      });
    });
  }

  // Display a notice indicating that the action was successful
  function successModelDirectoryNotice(message) {
    const $successNotice = $(".model-directory-success-notice");
    $successNotice.find(".notice-success-text").text(message);
    $successNotice.removeClass("d-none");
    $successNotice.removeClass("notice");
    void $successNotice[0].offsetWidth; // Trigger reflow to restart the animation
    $successNotice.addClass("notice");
  }

  // Display a notice indicating that the action encountered an error
  function dangerModelDirectoryNotice(message) {
    const $dangerNotice = $(".model-directory-danger-notice");
    $dangerNotice.find(".notice-danger-text").text(message);
    $dangerNotice.removeClass("d-none");
    $dangerNotice.removeClass("notice");
    void $dangerNotice[0].offsetWidth; // Trigger reflow to restart the animation
    $dangerNotice.addClass("notice");
  }

  function showLoadingSpinner() {
    $(".loading-background-container").removeClass("d-none");
  }
  function hideLoadingSpinner() {
    $(".loading-background-container").addClass("d-none");
  }

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  // Function to sort the model directory alphabetically
  function sortModelDirectoryAlphabetically($container) {
    const $elements = $container.children("ul");

    $elements.sort(function (a, b) {
      const $a = $(a).children("li").first();
      const $b = $(b).children("li").first();

      const aIsDirectory = $a.hasClass("is-directory");
      const bIsDirectory = $b.hasClass("is-directory");

      if (aIsDirectory && !bIsDirectory) {
        return -1; // a is a directory and b is a file
      } else if (!aIsDirectory && bIsDirectory) {
        return 1; // a is a file and b is a directory
      } else {
        const aText = $a.attr("key").toLowerCase();
        const bText = $b.attr("key").toLowerCase();
        return aText.localeCompare(bText); // Both are the same type, sort alphabetically
      }
    });

    $elements.detach().appendTo($container);
  }

  // Function to show the prompt modal to confirm the action
  function showModelPromptModal(action, path, filenames) {
    return new Promise((resolve, reject) => {
      // Error handling: Check if filenames is undefined
      if (typeof filenames === "undefined") {
        return reject("Filenames variable is unassigned or undefined");
      }
      // No files to overwrite/delete -> no need prompt
      else if (filenames === null) {
        return resolve(true);
      }
      // Multiple files to overwrite/delete -> join with <br> for better readability
      if (Array.isArray(filenames)) {
        if (filenames.length > 0) {
          filenames = filenames.join("<br>");
        }
        // No files to overwrite/delete -> no need prompt
        else {
          return resolve(true);
        }
      }
      // No files to overwrite/delete -> no need prompt
      else if (filenames.toString() === "") {
        return resolve(true);
      }
      // Single file to overwrite/delete -> convert to string
      else {
        filenames = filenames.toString();
      }

      // Set the path to "root" if it is empty
      if (path == "") {
        path = "root";
      }

      const $modal = $(".model-prompt-container");
      const $confirmBtn = $modal.find(".prompt-confirm-button");
      const $cancelBtn = $modal.find(".prompt-cancel-button");
      const $message = $modal.find(".prompt-body");

      // Construct the message to be displayed in the modal
      var htmlMessage =
        "<b>Are you sure want to " +
        action +
        " the following files?</b><br>" +
        "<br>" +
        "<b>Directory:</b> " +
        path +
        "<br>" +
        "<br>" +
        "<b>Files:</b><br>" +
        filenames;
      $message.html(htmlMessage);

      // Show the modal
      $modal.css("display", "block");

      // Event listener for confirm button
      $confirmBtn.click(() => {
        $modal.css("display", "none");
        resolve(true); // Resolve the promise with true
      });

      // Event listener for cancel button
      $cancelBtn.click(() => {
        $modal.css("display", "none");
        resolve(false); // Resolve the promise with true
      });
    });
  }

  // Read the contents of the directory recursively and return the list of files and directories
  async function readUploadDirectoryRecursively(directoryReader) {
    return new Promise((resolve, reject) => {
      const directoryContents = [];
      directoryReader.readEntries(async function (entries) {
        for (const entry of entries) {
          directoryContents.push(entry);
          if (entry.isDirectory) {
            const subDirectoryReader = entry.createReader();
            const subDirectoryContents =
              await readUploadDirectoryRecursively(subDirectoryReader);
            directoryContents.push(...subDirectoryContents);
          }
        }
        resolve(directoryContents);
      });
    });
  }

  // Sync the directory with the uploaded files
  function successUploadToDirectory(htmlContent, fileSet, $directory) {
    // Remove existing elements that are in the appended_set
    $directory.children("ul").each(function () {
      const $folder = $(this).children("li").first();
      if (fileSet.includes($folder.attr("key"))) {
        $(this).remove();
      }
    });

    // Append the new files to the directory
    $directory.append(htmlContent);
    $directory.removeClass("folder-collapse");
    sortModelDirectoryAlphabetically($directory);
  }

  // Expand and collapse directory
  $(".tree-explorer").on("click", "li", function (event) {
    const $directory = $(this).closest("ul");
    $directory.toggleClass("folder-collapse");
  });

  // Insert input field for naming the folder
  $(".tree-explorer").on("click", "li i.trigger-add-folder", function (event) {
    preventDefaults(event);

    const $directory = $(this).closest("ul");

    // Get the css value of the current directory
    const $folder = $(this).closest("li");
    var leftIndent =
      parseInt($folder.css("padding-left"), 10) + DIRECTORY_LEFT_INDENT;
    leftIndent = leftIndent + "px";
    const classList = $folder.attr("class");

    // Expand the directory
    $directory.removeClass("folder-collapse");

    // Append an input field to the current directory's <ul> to create a new subdirectory
    const $inputUl = $(
      '<ul id="new-folder"><li style="background-color:#EBEEFF;padding-left:' +
        leftIndent +
        '" class="' +
        classList +
        '"><input placeholder="New Folder Name" type="text" class="new-folder-name-input"/></li></ul>',
    );
    $directory.append($inputUl);

    // Set focus to the newly appended input field for entering the new folder name
    $inputUl.find("li input").focus();
  });

  // Filter input to allow only non-special characters (like Windows directory)
  $(".tree-explorer").on("input", "ul#new-folder input", function () {
    // Define a regular expression to match disallowed characters
    const disallowedCharacters = /[\\/:*?"<>|]/g;

    var currentValue = $(this).val();
    // Replace disallowed characters with an empty string
    if (disallowedCharacters.test(currentValue)) {
      dangerModelDirectoryNotice(
        'Special characters \\ / : * ? " < > | are not allowed in the folder name.',
      );
    }
    var sanitizedValue = currentValue.replace(disallowedCharacters, "");
    $(this).val(sanitizedValue);
  });

  // Create new folder at the directory once left the input field
  $(".tree-explorer").on("blur", "ul#new-folder input", async function () {
    // Get the path to the directory where the new folder is to be created
    const $directory = $(this).closest("ul").parent("ul");
    const directoryName = $directory.attr("path") || ""; // eg. path/to/directory/
    const $folder = $directory.children("li").first();
    const folderName = $folder.attr("key") || "";
    var path = directoryName + folderName;

    if (path === undefined || path === "undefined") {
      path = "";
    } else if (path.startsWith("/")) {
      path = path.substring(1);
    }

    // Get the name of the new folder
    const newFolderName = $(this).val();
    var $inputUl = $(this).closest("ul");
    $inputUl.remove();

    // Create new folder if input is not null
    if (newFolderName !== "") {
      // Create the new folder
      await createModelDirectory(path, newFolderName)
        // If the folder is successfully created
        .then((response) => {
          // Display a success notice
          successModelDirectoryNotice(response);

          // Load the files in the directory
          return loadModelDirectoryFiles(path, newFolderName);
        })
        // If the directory files are successfully loaded
        .then((response) => {
          // Append the new folder to the directory
          // Expand the folder and sort the directory alphabetically
          $directory.append(response);
          $directory.removeClass("folder-collapse");
          sortModelDirectoryAlphabetically($directory);
        })
        // Catch any errors that occur during the process
        .catch((error) => {
          console.error(error);
          dangerModelDirectoryNotice(error);
        });
    }
  });

  // Copy MODEL URL path to clipboard
  $(".tree-explorer").on("click", "li i.trigger-copy-path", function (event) {
    preventDefaults(event);

    const urlPath = $(this).closest("li").attr("title"); // MODEL_URL

    navigator.clipboard.writeText(urlPath).then(
      function () {
        successModelDirectoryNotice("Model URL path copied to clipboard.");
      },
      function (err) {
        dangerModelDirectoryNotice("Could not copy path to clipboard: " + err);
      },
    );
  });

  // Insert input file field for uploading file
  $(".tree-explorer").on("click", "li i.trigger-upload-file", function (event) {
    preventDefaults(event);

    // Get the path from the root to the current directory (e.g., "path/to/")
    const $directory = $(this).closest("ul");

    // Add an input field to the current directory's <ul> to upload a file
    const $inputUl = $(
      '<ul id="upload-folder"><input hidden type="file" class="upload-file-input"/></ul>',
    );
    $directory.append($inputUl);

    // Open upload file dialog
    $inputUl.find("input").click();
  });

  // Upload file to the directory
  $(".tree-explorer").on(
    "change cancel",
    "ul#upload-folder input[type='file']",
    async function () {
      // Extract the uploaded file
      const fileInput = $(this);
      const uploaded_file = fileInput[0].files[0];

      // Get the path to the directory where the new folder is to be created
      const $directory = $(this).closest("ul").parent("ul");
      const $inputUl = $(this).closest("ul");
      $inputUl.remove();

      // Upload file if input is not null
      const fileList = [];
      const directoryName = $directory.attr("path") || ""; // eg. path/to/directory/
      const $folder = $directory.children("li").first();
      const folderName = $folder.attr("key") || "";
      var path = directoryName + folderName;

      if (path === undefined || path === "undefined") {
        path = "";
      } else if (path.startsWith("/")) {
        path = path.substring(1);
      }

      if (uploaded_file) {
        try {
          // zip file case
          if (
            uploaded_file.type === "application/zip" ||
            uploaded_file.name.endsWith(".zip")
          ) {
            fileList.push(uploaded_file.name.split(".zip")[0]);
          }
          // Normal file case
          else {
            fileList.push(uploaded_file.name);
          }

          // Check if the file is already existed in the directory
          const fileOverwrite = [];
          await Promise.all(
            fileList.map(async (file) => {
              const response = await checkDirectoryExistence(path, file);
              if (response) {
                fileOverwrite.push(file);
              }
            }),
          );

          // Overwrite consent prompt
          if (fileOverwrite.length > 0) {
            const promptResponse = await showModelPromptModal(
              "overwrite",
              path,
              fileOverwrite,
            );
            if (promptResponse) {
              const deletePromises = fileOverwrite.map((file) =>
                deleteModelDirectory(path, file),
              );
              await Promise.all(deletePromises);
              successModelDirectoryNotice("Files are successfully deleted");
            } else {
              throw new Error("User canceled the overwrite operation");
            }
          }

          const fileSet = [];
          var message;
          // If user consent to overwrite the file
          if (uploaded_file.name.endsWith(".zip")) {
            // Extract zip file
            const zipName = uploaded_file.name.split(".zip")[0];
            fileSet.push(zipName);
            await createModelDirectory(path, zipName);
            var extractedPath = path;
            if (extractedPath !== "" && extractedPath[-1] !== "/") {
              extractedPath += "/";
            }
            extractedPath += zipName;
            message = await extractModelDirectoryFile(
              extractedPath,
              uploaded_file,
            );
          } else {
            // Upload normal file
            fileSet.push(uploaded_file.name);
            message = await uploadModelDirectoryFile(path, uploaded_file);
          }

          // Display a success notice
          successModelDirectoryNotice(message);

          const loadPromises = fileSet.map((file) =>
            loadModelDirectoryFiles(path, file),
          );
          const loadResponses = await Promise.all(loadPromises);

          let htmlContent = "";

          // Load all directory content
          loadResponses.forEach((response) => {
            htmlContent += response;
          });

          // Sync the directory with the uploaded files
          successUploadToDirectory(htmlContent, fileSet, $directory);
        } catch (error) {
          console.error(error);
          dangerModelDirectoryNotice(error);
          return;
        }
      } else {
        console.error("No file is uploaded");
        dangerModelDirectoryNotice("No file is uploaded");
      }
    },
  );

  // Drag and drop upload file
  $(".tree-explorer").on("drop", "ul", async function (event) {
    preventDefaults(event);

    // Get the path to the directory where the new content is to be uploaded
    var $droppedUl = $(this);
    const $folder = $droppedUl.children("li").first();
    var path = $droppedUl.attr("path") || ""; // eg. path/to/directory/

    // If is folder, append the folder to the directory tree
    if ($folder.hasClass("is-directory")) {
      path += $folder.attr("key") || "";
    } else if ($folder.hasClass("is-file")) {
      $droppedUl = $droppedUl.parent("ul");
    }

    if (path === undefined || path === "undefined") {
      path = "";
    } else if (path[0] === "/") {
      path = path.substring(1);
    }

    const droppedItems = [];
    const items = event.originalEvent.dataTransfer.items;
    for (var itemIndex = 0; itemIndex < items.length; itemIndex++) {
      const item = items[itemIndex].webkitGetAsEntry();
      if (item) {
        droppedItems.push(item);
      }
    }

    const droppedFiles = event.originalEvent.dataTransfer.files;
    var droppedNumber = 0;
    if (droppedItems.length === droppedFiles.length) {
      droppedNumber = droppedFiles.length;
    } else {
      console.error("Number of items and files are not equal");
      dangerModelDirectoryNotice("Number of items and files are not equal");
      return;
    }

    if (droppedNumber <= 0) {
      dangerModelDirectoryNotice("No file is dropped");
      return;
    }
    try {
      for (var droppedIndex = 0; droppedIndex < droppedNumber; droppedIndex++) {
        const item = droppedItems[droppedIndex];
        const file = droppedFiles[droppedIndex];
        const fileList = [];

        if (item.isDirectory) {
          // Directory case
          fileList.push(item.name);
        } else if (item.isFile) {
          // File case
          // ZIP file
          if (file.type === "application/zip" || file.name.endsWith(".zip")) {
            fileList.push(file.name.split(".zip")[0]);
          } else {
            fileList.push(file.name);
          }
        } else {
          throw new Error("Unknown file type");
        }

        // Check if the file is already existed in the directory
        const fileOverwrite = [];
        await Promise.all(
          fileList.map(async (file) => {
            const response = await checkDirectoryExistence(path, file);
            if (response) {
              fileOverwrite.push(file);
            }
          }),
        );

        // Overwrite consent prompt
        if (fileOverwrite.length > 0) {
          const promptResponse = await showModelPromptModal(
            "overwrite",
            path,
            fileOverwrite,
          );
          if (promptResponse) {
            const deletePromises = fileOverwrite.map((file) =>
              deleteModelDirectory(path, file),
            );
            await Promise.all(deletePromises);
            successModelDirectoryNotice("Files are successfully deleted");
          } else {
            dangerModelDirectoryNotice("User canceled the overwrite operation");
            continue;
          }
        }

        // If user consent to overwrite the file
        const fileSet = [];
        if (item.isDirectory) {
          fileSet.push(item.name);
          await createModelDirectory(path, item.name);

          const directoryReader = item.createReader();
          const fileContents = [];
          const entries = await readUploadDirectoryRecursively(directoryReader);

          // Process each entry in the directory
          for (const entry of entries) {
            if (entry.isFile) {
              fileContents.push(entry);
            } else if (entry.isDirectory) {
              const entryPath = entry.fullPath.startsWith("/")
                ? entry.fullPath.substring(1)
                : entry.fullPath;
              await createModelDirectory(path, entryPath);
            } else {
              throw new Error("Unknown file type");
            }
          }

          for (const fileEntry of fileContents) {
            // Relative file path to the uploaded_directory
            let entryPath = fileEntry.fullPath.split(fileEntry.name)[0];
            let completePath = path + entryPath;
            if (completePath[0] === "/") {
              completePath = completePath.substring(1);
            }

            await new Promise((resolve, reject) => {
              fileEntry.file(async (file) => {
                try {
                  await uploadModelDirectoryFile(completePath, file);
                  resolve(); // Resolve the promise after the file is uploaded
                } catch (error) {
                  reject(error);
                }
              });
            });
          }

          successModelDirectoryNotice("Directory is successfully uploaded");
        } else {
          var message;
          if (item.name.endsWith(".zip")) {
            // Extract zip file
            const zipName = file.name.split(".zip")[0];
            fileSet.push(zipName);
            await createModelDirectory(path, zipName);
            var extractedPath = path;
            if (extractedPath !== "" && extractedPath[-1] !== "/") {
              extractedPath += "/";
            }
            extractedPath += zipName;
            message = await extractModelDirectoryFile(extractedPath, file);
          } else {
            // Upload normal file
            fileSet.push(file.name);
            message = await uploadModelDirectoryFile(path, file);
          }
          successModelDirectoryNotice(message);
        }

        const loadPromises = fileSet.map((file) =>
          loadModelDirectoryFiles(path, file),
        );
        const loadResponses = await Promise.all(loadPromises);

        let htmlContent = "";

        // Load all directory content
        loadResponses.forEach((response) => {
          htmlContent += response;
        });

        // Sync the directory with the uploaded files
        successUploadToDirectory(htmlContent, fileSet, $droppedUl);
      }
    } catch (error) {
      console.error(error);
      dangerModelDirectoryNotice(error);
      return;
    }
  });

  // Delete the target file/folder
  $(".tree-explorer").on(
    "click",
    "li i.trigger-delete-folder",
    async function (event) {
      preventDefaults(event);

      // Get the path from the root to the current directory (e.g., "path/to")
      var $directory = $(this).closest("ul");
      var directoryName = $directory.attr("path") || "";

      // Get the name where a new folder/file is intended to be deleted (e.g., "target")
      var $folder = $(this).closest("li");
      var target = $folder.attr("key") || "";

      // Construct the full path to the target (e.g., "path/to/target")
      var path = directoryName + target;

      if (path === undefined || path === "undefined") {
        path = "";
      } else if (path.startsWith("/")) {
        path = path.substring(1);
      }

      await showModelPromptModal("delete", directoryName, target)
        .then((response) => {
          if (response) return deleteModelDirectory(directoryName, target);
          else return Promise.reject("User canceled the delete operation");
        })
        .then((response) => {
          $directory.remove();
          successModelDirectoryNotice(response);
        })
        .catch((error) => {
          console.error(error);
          dangerModelDirectoryNotice(error);
          return;
        });
    },
  );

  // Prevent default action for dragenter, dragover, and dragleave events
  $(".tree-explorer").on(
    "dragenter dragover dragleave",
    "ul",
    function (event) {
      preventDefaults(event);
    },
  );

  // Highlight the directory contents when mouse hover
  $(".tree-explorer").on("mouseenter", "li", function () {
    $(this).siblings().css("background-color", "#EBEEFF");
  });
  $(".tree-explorer").on("mouseleave", "li", function () {
    $(this).siblings().css("background-color", "");
  });
});
