create or replace function public.suppress_voice_contact(p_lead_id uuid, p_phone text)
returns boolean language plpgsql security definer set search_path = public, pg_temp
as $$
begin
  if p_phone is null or p_phone !~ '^\+[1-9][0-9]{7,14}$' then return false; end if;
  if p_lead_id is not null and not exists (
    select 1 from public.leads where id = p_lead_id and (owner_phone = p_phone or owner_phone_2 = p_phone)
  ) then return false; end if;
  insert into public.dnc_list(phone, reason) values (p_phone, 'verbal_stop_request')
  on conflict(phone) do update set reason = excluded.reason;
  update public.leads set opted_out = true, email_opted_out = true, dnc_blocked = true,
    callable = false, callback_scheduled_at = null, updated_at = now()
  where owner_phone = p_phone or owner_phone_2 = p_phone;
  return true;
end;
$$;
revoke all on function public.suppress_voice_contact(uuid, text) from public, anon, authenticated;
grant execute on function public.suppress_voice_contact(uuid, text) to service_role;
