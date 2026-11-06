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
  local envelope = task:get_from('smtp')
  -- sign_condition replaces Rspamd's normal mismatch checks. Postfix has
  -- already authorized the envelope against the authenticated mailbox and its
  -- SQL aliases on both submission ports. Bind the complete header identity to
  -- that authorized envelope before choosing any hosted domain's key.
  if not from or #from ~= 1 or not from[1].addr or not from[1].domain
      or not envelope or #envelope ~= 1 or not envelope[1].addr
      or string.lower(from[1].addr) ~= string.lower(envelope[1].addr) then
    task:set_pre_result('reject', 'From must match the authorized envelope sender', 'oo_sender_policy')
    return false
  end
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
