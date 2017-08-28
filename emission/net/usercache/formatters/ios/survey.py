import logging
import arrow

import emission.net.usercache.formatters.common as fc
import emission.storage.decorations.local_date_queries as ecsdlq
import attrdict as ad

def format(entry):
    formatted_entry = ad.AttrDict()
    formatted_entry["_id"] = entry["_id"]
    formatted_entry.user_id = entry.user_id
    
    metadata = entry.metadata
    if "time_zone" not in metadata:
        metadata.time_zone = "America/Los_Angeles"
    logging.debug("Timestamp conversion: %s -> %s done" % (entry.metadata.write_ts, metadata.write_ts))
    fc.expand_metadata_times(metadata)
    formatted_entry.metadata = metadata

    data = entry.data
    fc.expand_data_times(data, metadata)
    data.local_dt = ecsdlq.get_local_date(metadata.write_ts, metadata.time_zone)
    data.fmt_time = arrow.get(metadata.write_ts).to(metadata.time_zone).isoformat()
    formatted_entry.data = data

    logging.debug("RECEIVED iOS survey response: %s" % metadata.write_ts)

    return formatted_entry
