window.ThanatosPortal = {
  init: function() {
    console.log('Thanatos Portal initialized');
  },
  sendMessage: function(message) {
    console.log('Send message:', message);
  },
  uploadDocument: function(file) {
    console.log('Upload document:', file?.name || 'no-file');
  }
};

document.addEventListener('DOMContentLoaded', function(){
  window.ThanatosPortal.init();
});
