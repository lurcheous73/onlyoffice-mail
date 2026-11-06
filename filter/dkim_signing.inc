enabled = true;
sign_authenticated = true;
sign_local = false;
allow_hdrfrom_mismatch = false;
use_domain = "header";
try_fallback = false;
sign_condition = <<EOD
return function(task)
  if not task:get_user() then return false end
  local from = task:get_from('mime')
  if not from or not from[1] or not from[1].domain then return false end
  local f = io.open('/dkim/domains.json', 'r')
  if not f then return false end
  local raw=f:read('*a');f:close()
  local parser=require 'ucl';local p=parser.parser()
  if not p:parse_string(raw) then return false end
  local record=p:get_object()[string.lower(from[1].domain)]
  if not record then return false end
  return {key=record.path,selector=record.selector,domain=string.lower(from[1].domain)}
end
EOD;
