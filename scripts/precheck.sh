#!/bin/bash

set -e

# Check for WSL
if uname -a | grep -i microsoft > /dev/null ; then
    echo "WSL is not supported."
    exit 1
fi

# Check for required commands
for cmd in git curl make openssl; do
    if ! command -v $cmd > /dev/null; then
        echo "Missing required command: $cmd"
        exit 1
    fi
done

ok_password() {
    local pw="$1"
    local clean
    clean=$(echo "$pw" | sed -e 's/[- .,_/A-Za-z0-9]//g')
    if [ -n "$clean" ]; then
        return 1
    fi
    return 0
}

get_password() {
    local prompt="$1"
    local pw verify clean
    while true; do
        read -s -p "$prompt" pw
        echo
        if [ -z "$pw" ]; then
            echo "Please enter a password"
            continue
        fi
        if ! ok_password "$pw"; then
            echo "Please use only upper/lowercase letters, numbers, and the symbols -,_."
            continue
        fi
        read -s -p "Verify: " verify
        echo
        if [ "$pw" = "$verify" ]; then
            PASSWORD="$pw"
            break
        fi
        echo "Password and verify do not match"
    done
}

if [ -z "$SUPASS" ]; then
    echo 'Enter a "superuser" password (SUPASS) for logging in to the web interface.'
    echo "Acceptable characters are upper and lowercase letters, numbers, and the symbols -,_."
    get_password "Enter SUPASS: "
    SUPASS="$PASSWORD"
else
    if ! ok_password "$SUPASS"; then
        echo "Please use only upper/lowercase letters, numbers, and the symbols -,_. in SUPASS"
        exit 1
    fi
fi

if [ -z "$DBPASS" ]; then
    get_password "Enter DBPASS: "
    DBPASS="$PASSWORD"
else
    if ! ok_password "$DBPASS"; then
        echo "Please use only upper/lowercase letters, numbers, and the symbols -,_. in DBPASS"
        exit 1
    fi
fi

if [ -z "$CERTPASS" ]; then
    CERTPASS=$(openssl rand -base64 33)
else
    if ! ok_password "$CERTPASS"; then
        echo "Please use only upper/lowercase letters, numbers, and the symbols -,_. in CERTPASS"
        exit 1
    fi
fi

# Save to .env for Makefile usage
cat > .env <<EOF
SUPASS=${SUPASS}
DBPASS=${DBPASS}
CERTPASS=${CERTPASS}
EOF

echo ".env file created with credentials."