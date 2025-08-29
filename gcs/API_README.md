# GCS Frontend API Documentation

This document outlines the API endpoints available for frontend developers to interact with the Ground Control Station (GCS) for orthophoto management.

## Base URL

The API is expected to run on `http://localhost:5000`.

## Endpoints

### 1. Upload Orthophoto

- **URL:** `/upload`
- **Method:** `POST`
- **Description:** Uploads an orthophoto file to the GCS.
- **Request:**
  - `Content-Type`: `multipart/form-data`
  - **Form Field:** `file` (type: `File`) - The orthophoto file to upload.
- **Response (Success - 200 OK):**
  ```json
  {
    "message": "File [filename] uploaded successfully"
  }
  ```
- **Response (Error - 400 Bad Request):**
  ```json
  {
    "error": "No file part in the request"
  }
  ```
  or
  ```json
  {
    "error": "No selected file"
  }
  ```
- **Response (Error - 500 Internal Server Error):**
  ```json
  {
    "error": "Something went wrong"
  }
  ```

### 2. List Orthophotos

- **URL:** `/files`
- **Method:** `GET`
- **Description:** Retrieves a list of all orthophoto filenames currently stored on the GCS.
- **Request:** None
- **Response (Success - 200 OK):**
  ```json
  {
    "files": ["orthophoto1.jpg", "orthophoto2.png", "another_map.tif"]
  }
  ```
- **Response (Error - 500 Internal Server Error):**
  ```json
  {
    "error": "Could not list files"
  }
  ```

### 3. Download Specific Orthophoto

- **URL:** `/files/<filename>`
- **Method:** `GET`
- **Description:** Downloads a specific orthophoto file by its filename.
- **Request:** None
- **Path Parameters:**
  - `filename` (string, required): The name of the file to download.
- **Response (Success - 200 OK):**
  - The file content will be returned as an attachment.
- **Response (Error - 404 Not Found):**
  ```json
  {
    "error": "File not found"
  }
  ```
- **Response (Error - 500 Internal Server Error):**
  ```json
  {
    "error": "Could not download file"
  }
  ```

## Example Usage (JavaScript - Frontend)

### Upload a file:

```javascript
const uploadFile = async (file) => {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("http://localhost:5000/upload", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    console.log("Upload response:", data);
  } catch (error) {
    console.error("Error uploading file:", error);
  }
};

// Example: Assuming you have an input type="file" with id="orthophotoInput"
// const fileInput = document.getElementById('orthophotoInput');
// fileInput.addEventListener('change', (event) => {
//     const selectedFile = event.target.files[0];
//     if (selectedFile) {
//         uploadFile(selectedFile);
//     }
// });
```

### List files:

```javascript
const listFiles = async () => {
  try {
    const response = await fetch("http://localhost:5000/files");
    const data = await response.json();
    console.log("Available files:", data.files);
  } catch (error) {
    console.error("Error listing files:", error);
  }
};

// listFiles();
```

### Download a file:

```javascript
const downloadFile = (filename) => {
  window.open(`http://localhost:5000/files/${filename}`, "_blank");
};

// Example: downloadFile('orthophoto1.jpg');
```
