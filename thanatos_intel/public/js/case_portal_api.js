window.ThanatosPortalAPI = {
 async call(method,args={}){
   return frappe.call({
      method: method,
      args: args
   });
 },
 async loadDocuments(caseName){
   return this.call('thanatos_intel.thanatos_portal.api.document_upload.get_case_documents',{case_name:caseName});
 },
 async loadTimeline(caseName){
   return this.call('thanatos_intel.thanatos_portal.api.activity_timeline.get_case_activity',{case_name:caseName});
 }
};