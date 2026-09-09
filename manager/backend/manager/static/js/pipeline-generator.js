// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Initialize pipeline generation functionality when DOM is loaded
document.addEventListener("DOMContentLoaded", function () {
  console.log("Pipeline generator: DOM loaded, initializing...");

  const generateButton = document.getElementById("generate-pipeline-preview");
  const pipelineField = document.getElementById("id_camera_pipeline");
  const generatePipelineUrl = document.getElementById(
    "generate-pipeline-url",
  )?.value;

  console.log("Pipeline generator: Elements found:", {
    generateButton: !!generateButton,
    pipelineField: !!pipelineField,
    generatePipelineUrl: generatePipelineUrl,
  });

  if (generateButton && pipelineField && generatePipelineUrl) {
    console.log(
      "Pipeline generator: All elements found, attaching event listener...",
    );

    generateButton.addEventListener("click", function (e) {
      e.preventDefault();
      console.log("Pipeline generator: Generate button clicked!");

      // Disable button and show loading state
      generateButton.disabled = true;
      generateButton.innerHTML = "Generating...";

      // Get CSRF token
      const csrfToken = document.querySelector(
        "[name=csrfmiddlewaretoken]",
      )?.value;

      console.log("Pipeline generator: CSRF token found:", !!csrfToken);

      if (!csrfToken) {
        alert("CSRF token not found. Please refresh the page and try again.");
        generateButton.disabled = false;
        generateButton.innerHTML = "Generate Pipeline Preview";
        return;
      }

      // Collect all form data
      const formData = {};
      const form = document.getElementById("calibration_form");

      if (form) {
        const formElements = form.elements;
        for (let i = 0; i < formElements.length; i++) {
          const element = formElements[i];

          // Skip buttons, submit inputs, and CSRF token
          if (
            element.type === "button" ||
            element.type === "submit" ||
            element.name === "csrfmiddlewaretoken"
          ) {
            continue;
          }

          // Handle different input types
          if (element.type === "checkbox") {
            formData[element.name] = element.checked;
          } else if (element.type === "radio") {
            if (element.checked) {
              formData[element.name] = element.value;
            }
          } else if (element.type === "select-multiple") {
            const selectedValues = [];
            for (let option of element.options) {
              if (option.selected) {
                selectedValues.push(option.value);
              }
            }
            formData[element.name] = selectedValues;
          } else if (element.name && element.value !== "") {
            // Handle text, number, hidden, textarea, select-one, etc.
            formData[element.name] = element.value;
          }
        }
      }

      console.log("Pipeline generator: Form data collected:", formData);
      console.log(
        "Pipeline generator: Making fetch request to:",
        generatePipelineUrl,
      );

      // Make request to generate pipeline
      fetch(generatePipelineUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(formData),
      })
        .then((response) => {
          console.log(
            "Pipeline generator: Response received:",
            response.status,
          );
          return response.json();
        })
        .then((data) => {
          console.log("Pipeline generator: Response data:", data);
          if (data.pipeline) {
            // Update the camera_pipeline field with the generated pipeline
            pipelineField.value = data.pipeline;
            // Add success visual feedback
            pipelineField.style.backgroundColor = "#d4edda";
            setTimeout(() => {
              pipelineField.style.backgroundColor = "";
            }, 2000);
            console.log("Pipeline generator: Pipeline updated successfully");
          } else if (data.error) {
            alert("Error generating pipeline: " + data.error);
          }
        })
        .catch((error) => {
          console.error("Pipeline generator: Error:", error);
          alert(
            "Error generating pipeline. Please check the console for details.",
          );
        })
        .finally(() => {
          // Re-enable button and restore original text
          generateButton.disabled = false;
          generateButton.innerHTML = "Generate Pipeline Preview";
          console.log(
            "Pipeline generator: Request completed, button re-enabled",
          );
        });
    });
  } else {
    console.log("Pipeline generator: Required elements not found");
    if (!generateButton)
      console.log(
        "Pipeline generator: generate-pipeline-preview button not found",
      );
    if (!pipelineField)
      console.log("Pipeline generator: id_camera_pipeline field not found");
    if (!generatePipelineUrl)
      console.log(
        "Pipeline generator: generate-pipeline-url hidden input not found",
      );
  }
});
