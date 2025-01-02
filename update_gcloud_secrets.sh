#!/bin/sh 

while read line; do
    # Skip empty lines and comments
    case "$line" in
        ''|\#*) continue ;;
    esac
    
    # Get key and value
    key=$(echo "$line" | cut -d '=' -f 1)
    value=$(echo "$line" | cut -d '=' -f 2-)
    
    # Skip if key is empty
    [ -z "$key" ] && continue
    
    echo "Updating secret $key"
    echo "$value" | gcloud secrets versions add "$key" --data-file=-
done < .env
