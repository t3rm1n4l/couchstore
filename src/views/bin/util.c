/* -*- Mode: C; tab-width: 4; c-basic-offset: 4; indent-tabs-mode: nil -*- */

/**
 * @copyright 2014 Couchbase, Inc.
 *
 * @author Sarath Lakshman  <sarath@couchbase.com>
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 **/

#include "util.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

static void exit_thread_helper(void *args)
{
    char buf[4];
    (void) args;

    if (fread(buf, 1, 4, stdin) == 4 && !strncmp(buf, "exit", 4)) {
        exit(1);
    }
}

/* Start a watcher thread to gracefully die on exit message */
int start_exit_listener(cb_thread_t *id)
{

    int ret = cb_create_thread(id, exit_thread_helper, NULL, 1);
    if (ret < 0) {
        /* For differentiating from couchstore_error_t */
        return -ret;
    }

    return ret;
}
