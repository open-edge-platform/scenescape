#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

UBUNTUPKGMAIN="https://packages.ubuntu.com"
UBUNTUPKGURL="${UBUNTUPKGMAIN}/source"

UBUNTUVERSIONBASE="focal"
UBUNTUVERSION="focal-updates"

FILE=$1

while read -r line
do

    NAME=$( echo $line | grep "Package: " | awk '{print $2}')
    if [[ "$NAME" != "" ]]
    then

        read -r line

        CURVER=$( echo $line | grep "Version: " | awk '{print $2}' )


        echo "IMAGE has pkg $NAME w/ version :${CURVER}:"
        wget ${UBUNTUPKGMAIN}/${UBUNTUVERSION}/${NAME} -O tmp.html --quiet
        wget ${UBUNTUPKGMAIN}/${UBUNTUVERSIONBASE}/${NAME} -O tmp_base.html --quiet

        URL=$( grep "\.dsc" tmp.html | sed -e 's@.*"\(.*\)".*@\1@g' )
        URLBASE=$( grep "\.dsc" tmp_base.html | sed -e 's@.*"\(.*\)".*@\1@g' )

        if [[ "$URL" != "" ]]
        then

            wget ${URL} -O tmp_desc.html --quiet

            LASTBINARY=$( grep "Binary: " tmp_desc.html | head -n 1 | cut -c 9- )
            LASTVERSION=$( grep "^Version: " tmp_desc.html | head -n 1 | cut -c 10- )

            #echo $( egrep '^Version: ' tmp_desc.html )

            LASTBINARY=${LASTBINARY%\\n}
            LASTVERSION=${LASTVERSION%\\n}

            if [[ "$LASTVERSION" != "$CURVER" ]]
            then

                echo "Version mismatch?"
                echo "BINARY :${LASTBINARY}:"
                echo "VERSION :${LASTVERSION}:"
                echo "$NAME has $CURVER and latest is $LASTVERSION (covers $LASTBINARY)"


            else
                echo "VERSION ${CURVER} matches latest available."
            fi

            echo ""


        else
            #echo "Package not at ${UBUNTUVERSION}!"
            if [[ "$URLBASE" != "" ]]
            then

                wget ${URLBASE} -O tmp_desc.html --quiet

                LASTBINARY=$( grep "Binary: " tmp_desc.html | head -n 1 | cut -c 9- )
                LASTVERSION=$( grep "^Version: " tmp_desc.html | head -n 1 | cut -c 10- )

                #echo $( egrep '^Version: ' tmp_desc.html )

                LASTBINARY=${LASTBINARY%\\n}
                LASTVERSION=${LASTVERSION%\\n}

                if [[ "$LASTVERSION" != "$CURVER" ]]
                then

                    echo "Version mismatch?"
                    echo "BINARY :${LASTBINARY}:"
                    echo "VERSION :${LASTVERSION}:"
                    echo "$NAME has $CURVER and latest is $LASTVERSION (covers $LASTBINARY)"

                else
                    echo "VERSION ${CURVER} matches latest available."
                fi
            else

                echo "Package not at ${UBUNTUVERSIONBASE}!"



            fi

        fi

        echo ""

        #exit
    fi

done < $FILE
