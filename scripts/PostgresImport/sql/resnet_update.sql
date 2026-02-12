set search_path to xxxx;

--sentence count
update control set num_sentences = count from (select count(reference.id) as count, control.id from reference, control where reference.id = control.attributes group by control.id)a  where a.id = control.id;
--reference count
update control set num_refs = count from (select count(distinct reference.unique_ref) as count, control.id from reference, control where reference.id = control.attributes group by control.id)a  where a.id = control.id;