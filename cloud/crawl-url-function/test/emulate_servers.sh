#! /usr/bin/bash -e
#
# Starts the PubSub emulator and then runs the remaining arguments.

if [ -z "$FIRESTORE_EMULATOR_HOST" -o -z "$PUBSUB_EMULATOR_HOST" ]; then
    firestore_env_file=$(mktemp)
    pubsub_out_file=$(mktemp)

    gcloud beta emulators firestore start &> $firestore_env_file &
    firestore_pid=$!

    gcloud beta emulators pubsub start &> $pubsub_out_file &
    pubsub_pid=$!

    trap "pkill -INT --pgroup $pubsub_pid,$firestore_pid; rm $firestore_env_file $pubsub_out_file" EXIT

    while ! grep -q 'Server started' $pubsub_out_file; do
      sleep 1
    done

    while ! grep -q 'Dev App Server is now running' $firestore_env_file; do
      sleep 1
    done

    $(gcloud beta emulators pubsub env-init)

    $(grep "export FIRESTORE_EMULATOR_HOST" $firestore_env_file|sed -e 's/\[firestore]//')
fi

# Move this to a python script...
#gcloud pubsub topics create crawl --project=$PROJECT

"$@"
