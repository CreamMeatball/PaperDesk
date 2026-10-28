// Drag-and-drop contract shared by the sidebar and the library table.
export var DOC_TYPE = "application/x-paperdesk-doc";
export var FOLDER_TYPE = "application/x-paperdesk-folder";

export function hasFiles(event) {
  return Array.prototype.indexOf.call(event.dataTransfer.types, "Files") >= 0;
}

export function pdfFiles(list) {
  return Array.prototype.filter.call(list || [], function (file) {
    return file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  });
}

// Make element a drop target for papers, folders and PDF files. target: folder id or null (= unfiled / top level).
export function makeDropTarget(element, app, target) {
  function accepts(event) {
    var types = event.dataTransfer.types;
    return hasFiles(event) || types.indexOf(DOC_TYPE) >= 0 || types.indexOf(FOLDER_TYPE) >= 0;
  }
  element.addEventListener("dragover", function (event) {
    if (!accepts(event)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = hasFiles(event) ? "copy" : "move";
    element.classList.add("drop");
  });
  element.addEventListener("dragleave", function () { element.classList.remove("drop"); });
  element.addEventListener("drop", function (event) {
    element.classList.remove("drop");
    if (!accepts(event)) return;
    event.preventDefault();
    event.stopPropagation();
    var docId = event.dataTransfer.getData(DOC_TYPE);
    var folderId = event.dataTransfer.getData(FOLDER_TYPE);
    if (docId) app.moveDocuments(docId.split(","), target);
    else if (folderId) app.moveFolder(folderId, target);
    else app.importFiles(pdfFiles(event.dataTransfer.files), target);
  });
}

